import React,{useEffect,useState} from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { C } from '../theme';
import { analysis } from '../api';
import { Pill, Score, signalColor } from '../components';

export default function StockDetailScreen({symbol,onBack}:{symbol:string;onBack:()=>void}){
 const [d,setD]=useState<any>(null);const [err,setErr]=useState('');const [busy,setBusy]=useState(true);
 async function load(refresh=false){setBusy(true);setErr('');try{setD(await analysis(symbol,refresh));}catch(e:any){setErr(e.message||'Could not load analysis');}finally{setBusy(false);}}
 useEffect(()=>{load(false)},[symbol]);
 return <ScrollView style={s.wrap} contentContainerStyle={s.content}><Pressable onPress={onBack}><Text style={s.back}>‹ Back</Text></Pressable>{busy&&!d?<ActivityIndicator style={{marginTop:40}} color={C.green}/>:err?<Text style={s.error}>{err}</Text>:d?<>
  <View style={s.head}><View><Text style={s.symbol}>{symbol}</Text><Text style={s.company}>{d.fundamentals?.companyName||d.company_name||''}</Text></View><Pill text={d.action||'WATCH'} tone={signalColor(d.action)}/></View>
  <Text style={s.price}>{d.currency||'$'} {Number(d.price||0).toFixed(2)}</Text><View style={s.scores}><Score label="Deterministic" value={d.deterministic_score}/><Score label="AI" value={d.ai_score}/><Score label="Analyst" value={d.analyst_score}/></View>
  <View style={s.block}><Text style={s.blockTitle}>Entry & risk</Text><Text style={s.row}>Primary buy  {fmtRange(d.levels?.primary_buy_low,d.levels?.primary_buy_high)}</Text><Text style={s.row}>Better buy   {fmtRange(d.levels?.better_buy_low,d.levels?.better_buy_high)}</Text><Text style={s.row}>Target       {fmt(d.levels?.target)}</Text><Text style={s.row}>Stop         {fmt(d.levels?.stop)}</Text><Text style={s.row}>Risk / reward {d.risk_reward?Number(d.risk_reward).toFixed(2):'—'}</Text></View>
  <View style={s.block}><Text style={s.blockTitle}>Deterministic breakdown</Text>{Object.entries(d.breakdown||{}).map(([k,v]:any)=><View key={k} style={s.breakRow}><Text style={s.row}>{k}</Text><Text style={s.breakValue}>{typeof v==='number'?v.toFixed(1):String(v)}</Text></View>)}</View>
  <View style={s.block}><Text style={s.blockTitle}>Why</Text>{(d.reasons||[]).slice(0,8).map((x:string,i:number)=><Text key={i} style={s.bullet}>• {x}</Text>)}{d.action_reason?<Text style={s.bullet}>• {d.action_reason}</Text>:null}</View>
  <View style={s.block}><Text style={s.blockTitle}>Risks / counterevidence</Text>{(d.risks||[]).slice(0,8).map((x:string,i:number)=><Text key={i} style={s.bullet}>• {x}</Text>)}</View>
  <Pressable onPress={()=>load(true)} disabled={busy} style={s.refresh}>{busy?<ActivityIndicator color={C.bg}/>:<Text style={s.refreshText}>Refresh full analysis</Text>}</Pressable>
 </>:null}</ScrollView>
}
function fmt(v:any){return v==null?'—':Number(v).toFixed(2)} function fmtRange(a:any,b:any){return a==null||b==null?'—':`${Number(a).toFixed(2)} – ${Number(b).toFixed(2)}`}
const s=StyleSheet.create({wrap:{flex:1,backgroundColor:C.bg},content:{padding:16,paddingBottom:80},back:{color:C.cyan,fontSize:16,fontWeight:'800',marginTop:8},head:{flexDirection:'row',justifyContent:'space-between',alignItems:'flex-start',marginTop:16},symbol:{color:C.text,fontSize:34,fontWeight:'900'},company:{color:C.muted,fontSize:12,marginTop:3},price:{color:C.text,fontSize:22,fontWeight:'800',marginTop:14},scores:{flexDirection:'row',gap:8,marginTop:14},block:{backgroundColor:C.panel,borderRadius:18,padding:16,borderWidth:1,borderColor:C.border,marginTop:14},blockTitle:{color:C.text,fontSize:16,fontWeight:'900',marginBottom:10},row:{color:C.muted,fontSize:13,lineHeight:21},breakRow:{flexDirection:'row',justifyContent:'space-between'},breakValue:{color:C.text,fontWeight:'800'},bullet:{color:C.muted,fontSize:13,lineHeight:20,marginBottom:4},refresh:{backgroundColor:C.green,borderRadius:14,padding:14,alignItems:'center',marginTop:18},refreshText:{color:C.bg,fontWeight:'900'},error:{color:C.red,marginTop:30}});
