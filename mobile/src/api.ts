import * as SecureStore from 'expo-secure-store';
import type { Bootstrap, CopilotMode, CopilotResponse } from './types';

const API_URL=(process.env.EXPO_PUBLIC_API_URL || 'https://isk-trading-radar.onrender.com').replace(/\/$/,'');
const TOKEN_KEY='isk_radar_mobile_token';

async function token(){ return SecureStore.getItemAsync(TOKEN_KEY); }

async function request<T>(path:string, init:RequestInit={}):Promise<T>{
  const t=await token();
  const headers:Record<string,string>={ 'Content-Type':'application/json', ...(init.headers as Record<string,string> || {}) };
  if(t) headers.Authorization=`Bearer ${t}`;
  const r=await fetch(`${API_URL}${path}`,{...init,headers});
  const text=await r.text();
  let data:any={};
  try{ data=text ? JSON.parse(text) : {}; }catch{ data={detail:text}; }
  if(!r.ok) throw new Error(data.detail || data.message || `Request failed (${r.status})`);
  return data as T;
}

export async function login(username:string,password:string){
  const data=await request<{token:string;username:string}>('/api/mobile/login',{method:'POST',body:JSON.stringify({username,password})});
  await SecureStore.setItemAsync(TOKEN_KEY,data.token);
  return data;
}
export async function logout(){ await SecureStore.deleteItemAsync(TOKEN_KEY); }
export async function hasToken(){ return Boolean(await token()); }
export async function bootstrap(){ return request<Bootstrap>('/api/mobile/bootstrap'); }
export async function analyze(query:string){ return request<{ok:boolean;symbol:string;name:string}>('/api/mobile/analyze',{method:'POST',body:JSON.stringify({query})}); }
export async function analysis(symbol:string,refresh=false){ return request<any>(`/api/mobile/analysis/${encodeURIComponent(symbol)}${refresh?'?refresh=1':''}`); }
export async function setRiskProfile(risk_profile:string){ return request('/api/mobile/risk-profile',{method:'POST',body:JSON.stringify({risk_profile})}); }
export async function ackAlert(id:number){ return request(`/api/mobile/alerts/${id}/ack`,{method:'POST'}); }
export async function dismissAlert(id:number){ return request(`/api/mobile/alerts/${id}/dismiss`,{method:'POST'}); }
export async function snoozeAlert(id:number,minutes=60){ return request(`/api/mobile/alerts/${id}/snooze`,{method:'POST',body:JSON.stringify({minutes})}); }
export async function copilot(mode:CopilotMode,message:string){ return request<CopilotResponse>('/api/mobile/copilot',{method:'POST',body:JSON.stringify({mode,message})}); }
export async function applyCopilot(action:string,value?:string){ return request<{ok:boolean;message:string}>('/api/mobile/copilot/apply',{method:'POST',body:JSON.stringify({action,value})}); }
export async function diagnostics(){ return request<any>('/api/mobile/diagnostics'); }
export { API_URL };
