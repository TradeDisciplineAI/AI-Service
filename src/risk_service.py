from uuid import UUID
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from src.config import risk_settings
from src.database import TradeProposal, RiskEvaluation, MarketPortfolio, MarketPaperPosition
from src.schemas import RiskCheckResultSchema, SignalAction

class RiskService:
    def evaluate_proposal(self, db: Session, proposal_id: UUID, current_user_id: UUID) -> Optional[RiskEvaluation]:
        # 1. Fetch proposal
        proposal = db.query(TradeProposal).filter(TradeProposal.id == proposal_id).first()
        if not proposal:
            return None

        # 2. Verify requesting user ownership
        if proposal.user_id != current_user_id:
            raise PermissionError("User does not own this trade proposal.")

        # 3. Verify status is PENDING_RISK
        if proposal.status != "PENDING_RISK":
            raise ValueError(f"Proposal cannot be evaluated in status: {proposal.status}")

        # 4. Verify action is BUY or SELL
        if proposal.action not in [SignalAction.BUY, SignalAction.SELL]:
            raise ValueError(f"HOLD proposals cannot enter risk evaluation.")

        # 5. Extract and validate required inputs
        quantity = proposal.requested_quantity
        entry_price = float(proposal.entry_price) if proposal.entry_price is not None else 0.0
        stop_loss = float(proposal.stop_loss) if proposal.stop_loss is not None else 0.0
        take_profit = float(proposal.take_profit) if proposal.take_profit is not None else 0.0

        checks: List[Dict[str, Any]] = []
        reasons: List[str] = []
        is_price_valid = True

        # Check basic numeric inputs
        if quantity <= 0:
            is_price_valid = False
            reasons.append("Quantity must be greater than zero.")
        if entry_price <= 0.0 or stop_loss <= 0.0 or take_profit <= 0.0:
            is_price_valid = False
            reasons.append("Entry price, stop loss, and take profit must be greater than zero.")

        # Check direction boundaries
        if is_price_valid:
            if proposal.action == SignalAction.BUY:
                if not (stop_loss < entry_price < take_profit):
                    is_price_valid = False
                    reasons.append(f"Invalid BUY price structure: stop loss ({stop_loss}) must be below entry ({entry_price}), which must be below take profit ({take_profit}).")
            elif proposal.action == SignalAction.SELL:
                if not (take_profit < entry_price < stop_loss):
                    is_price_valid = False
                    reasons.append(f"Invalid SELL price structure: take profit ({take_profit}) must be below entry ({entry_price}), which must be below stop loss ({stop_loss}).")

        checks.append({
            "check_name": "price_validity",
            "passed": is_price_valid,
            "severity": "CRITICAL",
            "actual_value": f"qty={quantity}, entry={entry_price}, sl={stop_loss}, tp={take_profit}",
            "limit_value": "positive numbers with valid order",
            "message": "Price ordering and quantities are valid." if is_price_valid else "; ".join(reasons)
        })

        # Critical Validation Failure
        if not is_price_valid:
            evaluation = RiskEvaluation(
                proposal_id=proposal_id,
                decision="RISK_REJECTED",
                risk_score=0,
                max_risk=0.0,
                estimated_reward=0.0,
                risk_reward_ratio=0.0,
                portfolio_exposure=0.0,
                checks=checks,
                reasons=reasons
            )
            proposal.status = "RISK_REJECTED"
            db.add(evaluation)
            db.commit()
            db.refresh(evaluation)
            return evaluation

        # 6. Perform risk math
        if proposal.action == SignalAction.BUY:
            risk_per_share = entry_price - stop_loss
            reward_per_share = take_profit - entry_price
        else:
            risk_per_share = stop_loss - entry_price
            reward_per_share = entry_price - take_profit

        total_trade_risk = risk_per_share * quantity
        estimated_reward = reward_per_share * quantity
        risk_reward_ratio = estimated_reward / total_trade_risk if total_trade_risk > 0 else 0.0
        position_value = quantity * entry_price

        # Retrieve Portfolio exposure
        portfolio_id = proposal.portfolio_id
        current_exposure = 0.0
        existing_symbol_exposure = 0.0

        if portfolio_id:
            # Verify portfolio exists
            portfolio = db.query(MarketPortfolio).filter(MarketPortfolio.id == portfolio_id).first()
            if not portfolio:
                reasons.append("Associated portfolio does not exist.")
                evaluation = RiskEvaluation(
                    proposal_id=proposal_id,
                    decision="RISK_REJECTED",
                    risk_score=0,
                    max_risk=total_trade_risk,
                    estimated_reward=estimated_reward,
                    risk_reward_ratio=risk_reward_ratio,
                    portfolio_exposure=0.0,
                    checks=checks + [{
                        "check_name": "portfolio_existence",
                        "passed": False,
                        "severity": "CRITICAL",
                        "actual_value": "portfolio missing",
                        "limit_value": "portfolio must exist",
                        "message": "Portfolio not found in market schema."
                    }],
                    reasons=["Associated portfolio does not exist."]
                )
                proposal.status = "RISK_REJECTED"
                db.add(evaluation)
                db.commit()
                db.refresh(evaluation)
                return evaluation

            # Fetch open paper positions
            positions = db.query(MarketPaperPosition).filter(MarketPaperPosition.portfolio_id == portfolio_id).all()
            current_exposure = sum(pos.quantity * float(pos.average_entry_price) for pos in positions)
            existing_symbol_exposure = sum(pos.quantity * float(pos.average_entry_price) for pos in positions if pos.symbol == proposal.symbol)

        projected_exposure = current_exposure + position_value
        projected_symbol_exposure = existing_symbol_exposure + position_value

        # Define check statuses
        # 1. Position Value check
        pv_passed = position_value <= risk_settings.MAX_POSITION_VALUE
        checks.append({
            "check_name": "position_value",
            "passed": pv_passed,
            "severity": "HIGH",
            "actual_value": f"{position_value:.2f}",
            "limit_value": f"{risk_settings.MAX_POSITION_VALUE:.2f}",
            "message": "Position value is within the limit." if pv_passed else f"Position value exceeds max allowed limit of {risk_settings.MAX_POSITION_VALUE}."
        })

        # 2. Monetary Risk check
        risk_passed = total_trade_risk <= risk_settings.MAX_TRADE_RISK
        checks.append({
            "check_name": "max_trade_risk",
            "passed": risk_passed,
            "severity": "HIGH",
            "actual_value": f"{total_trade_risk:.2f}",
            "limit_value": f"{risk_settings.MAX_TRADE_RISK:.2f}",
            "message": "Trade risk is within the configured limit." if risk_passed else f"Trade risk exceeds max allowed limit of {risk_settings.MAX_TRADE_RISK}."
        })

        # 3. Stop Distance check
        stop_dist = (abs(entry_price - stop_loss) / entry_price) * 100
        stop_passed = stop_dist <= risk_settings.MAX_STOP_DISTANCE_PERCENT
        checks.append({
            "check_name": "stop_loss_distance",
            "passed": stop_passed,
            "severity": "MEDIUM",
            "actual_value": f"{stop_dist:.2f}%",
            "limit_value": f"{risk_settings.MAX_STOP_DISTANCE_PERCENT:.2f}%",
            "message": "Stop loss distance is acceptable." if stop_passed else f"Stop loss distance exceeds maximum allowable distance of {risk_settings.MAX_STOP_DISTANCE_PERCENT}%."
        })

        # 4. Risk/Reward check
        rr_passed = risk_reward_ratio >= risk_settings.MIN_RISK_REWARD
        checks.append({
            "check_name": "risk_reward_ratio",
            "passed": rr_passed,
            "severity": "MEDIUM",
            "actual_value": f"{risk_reward_ratio:.2f}",
            "limit_value": f"{risk_settings.MIN_RISK_REWARD:.2f}",
            "message": "Risk reward ratio is acceptable." if rr_passed else f"Risk reward ratio is below minimum required of {risk_settings.MIN_RISK_REWARD}."
        })

        # 5. Portfolio total exposure check
        port_passed = projected_exposure <= risk_settings.MAX_PORTFOLIO_EXPOSURE
        checks.append({
            "check_name": "portfolio_total_exposure",
            "passed": port_passed,
            "severity": "HIGH",
            "actual_value": f"{projected_exposure:.2f}",
            "limit_value": f"{risk_settings.MAX_PORTFOLIO_EXPOSURE:.2f}",
            "message": "Projected portfolio total exposure is acceptable." if port_passed else f"Projected portfolio total exposure exceeds limit of {risk_settings.MAX_PORTFOLIO_EXPOSURE}."
        })

        # 6. Single asset exposure concentration check
        asset_passed = projected_symbol_exposure <= risk_settings.MAX_SINGLE_ASSET_EXPOSURE
        sell_note = " (SELL direction treated as gross exposure concentration limit)" if proposal.action == SignalAction.SELL else ""
        checks.append({
            "check_name": "single_asset_exposure",
            "passed": asset_passed,
            "severity": "HIGH",
            "actual_value": f"{projected_symbol_exposure:.2f}",
            "limit_value": f"{risk_settings.MAX_SINGLE_ASSET_EXPOSURE:.2f}",
            "message": f"Single asset exposure is acceptable.{sell_note}" if asset_passed else f"Single asset concentration exceeds limit of {risk_settings.MAX_SINGLE_ASSET_EXPOSURE}.{sell_note}"
        })

        # Determine Decision and Reasons
        score = 100
        decision = "RISK_APPROVED"

        # Calculate explainable score
        if not pv_passed:
            score -= 20
            reasons.append("Position value exceeds configured threshold.")
        if not risk_passed:
            score -= 20
            reasons.append("Monetary trade risk exceeds configured threshold.")
        if not stop_passed:
            score -= 15
            reasons.append("Stop-loss distance exceeds configured threshold.")
        if not rr_passed:
            score -= 15
            reasons.append("Risk/reward ratio is below configured threshold.")
        if not port_passed:
            score -= 15
            reasons.append("Portfolio total exposure exceeds configured threshold.")
        if not asset_passed:
            score -= 15
            reasons.append("Single asset concentration exceeds configured threshold.")

        # Determine decision based on severities
        failed_high = not (pv_passed and risk_passed and port_passed and asset_passed)
        failed_medium = not (stop_passed and rr_passed)

        if failed_high:
            decision = "RISK_REJECTED"
        elif failed_medium:
            decision = "NEEDS_REVIEW"

        # Save risk evaluation
        evaluation = RiskEvaluation(
            proposal_id=proposal_id,
            decision=decision,
            risk_score=score,
            max_risk=total_trade_risk,
            estimated_reward=estimated_reward,
            risk_reward_ratio=risk_reward_ratio,
            portfolio_exposure=projected_exposure,
            checks=checks,
            reasons=reasons
        )
        proposal.status = decision
        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)

        return evaluation

    def get_latest_evaluation(self, db: Session, proposal_id: UUID, current_user_id: UUID) -> Optional[RiskEvaluation]:
        # Fetch proposal to verify ownership
        proposal = db.query(TradeProposal).filter(TradeProposal.id == proposal_id).first()
        if not proposal:
            return None

        if proposal.user_id != current_user_id:
            raise PermissionError("User does not own this trade proposal.")

        # Get latest evaluation (since multiple history records might exist, sorted by evaluated_at desc)
        return db.query(RiskEvaluation).filter(RiskEvaluation.proposal_id == proposal_id).order_by(RiskEvaluation.evaluated_at.desc()).first()
