export type Signal = 'STRONG BUY'|'BUY'|'STARTER BUY'|'CONSIDER BUY'|'TAKE PROFIT'|'TAKE PARTIAL PROFIT'|'REBALANCE'|'ROTATE'|'REDUCE'|'EXIT'|'HOLD'|'WATCH'|string;

export type AlertItem = {
  id:number; symbol:string; title:string; message:string; severity?:string; action:Signal; alert_type?:string; created_at?:string|null;
};

export type Candidate = {
  symbol:string; name?:string; price:number; currency?:string; category?:string; score:number; ai_score:number;
  analyst_score?:number|null; analyst_label?:string; action?:string; action_reason?:string; system_signal:Signal;
  owned?:boolean; owned_shares?:number; owned_avg?:number; level_label?:string; level_value?:number|string|null;
  distance?:number|string|null; distance_pct?:number|null; target?:number|null; stop?:number|null; risk_reward?:number|null;
  expected_yield_pct?:number|null; stock_risk?:number; risk_band?:string; risk_fit?:string; suggested_shares?:number;
  suggested_capital?:number; sizing_reason?:string; projected_risk?:number|null; changed?:string|null; updated_at?:string|null;
};

export type Position = {
  id:number; symbol:string; shares:number; avg_cost:number; account?:string; price:number; pnl?:number|null; action?:string;
  ai_score?:number|null; currency?:string; value_base?:number; stock_risk?:number; sector?:string; system_signal?:Signal;
};

export type Bootstrap = {
  market_open:boolean; scanner_running:boolean; last_scan?:string|null; last_error?:string|null; universe_size:number;
  risk_profile:string; account_risk:{score?:number; band?:string; [key:string]:unknown}; summary:Record<string,unknown>;
  base_currency:string; cash:number; reserve:number; positions:Position[]; proposals:any[]; candidates:Candidate[]; alerts:AlertItem[];
  poll_seconds:number;
};

export type CopilotMode = 'ASK'|'CONFIGURE'|'DIAGNOSE'|'FIX';
export type CopilotProposal = { action:string; value?:string; label:string };
export type CopilotResponse = { reply:string; mode:CopilotMode; proposal?:CopilotProposal|null; diagnostics?:any; ai_assisted?:boolean; requires_engineering_connector?:boolean };
