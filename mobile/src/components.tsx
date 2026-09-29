import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { C } from './theme';
import type { Candidate, Signal } from './types';

export function signalColor(signal?:Signal){
  const s=(signal||'').toUpperCase();
  if(['STRONG BUY','BUY','STARTER BUY'].includes(s)) return C.green;
  if(['CONSIDER BUY','REBALANCE','ROTATE','TAKE PROFIT','TAKE PARTIAL PROFIT'].includes(s)) return C.yellow;
  if(['REDUCE','EXIT','SELL','STRONG SELL'].includes(s)) return C.red;
  return C.muted;
}

export function Pill({text,tone}:{text:string;tone?:string}){
  return <View style={[styles.pill,{borderColor:tone||C.border}]}><Text style={[styles.pillText,{color:tone||C.text}]}>{text}</Text></View>;
}

export function Score({label,value}:{label:string;value?:number|null}){
  return <View style={styles.score}><Text style={styles.scoreLabel}>{label}</Text><Text style={styles.scoreValue}>{value==null?'—':Math.round(value)}</Text></View>;
}

export function CandidateCard({c,onPress}:{c:Candidate;onPress?:()=>void}){
  const tone=signalColor(c.system_signal);
  return <Pressable onPress={onPress} style={({pressed})=>[styles.card,pressed&&{opacity:.8}]}>
    <View style={styles.row}><View><Text style={styles.symbol}>{c.symbol}</Text><Text numberOfLines={1} style={styles.name}>{c.name||c.symbol}</Text></View><Pill text={c.system_signal} tone={tone}/></View>
    <View style={styles.priceRow}><Text style={styles.price}>{c.currency||'$'} {Number(c.price||0).toFixed(2)}</Text><Text style={styles.level}>{c.level_label||'—'}</Text></View>
    <View style={styles.scores}><Score label="System" value={c.score}/><Score label="AI" value={c.ai_score}/><Score label="Risk" value={c.stock_risk}/></View>
    <View style={styles.metaRow}><Text style={styles.meta}>Target {c.target?Number(c.target).toFixed(2):'—'}</Text><Text style={styles.meta}>Stop {c.stop?Number(c.stop).toFixed(2):'—'}</Text><Text style={styles.meta}>R/R {c.risk_reward?Number(c.risk_reward).toFixed(1):'—'}</Text></View>
    {c.suggested_shares ? <Text style={styles.suggest}>Suggested: {c.suggested_shares} shares</Text> : null}
  </Pressable>;
}

export function SectionTitle({children}:{children:React.ReactNode}){ return <Text style={styles.section}>{children}</Text>; }

const styles=StyleSheet.create({
  card:{backgroundColor:C.panel,borderColor:C.border,borderWidth:1,borderRadius:18,padding:16,marginBottom:12},
  row:{flexDirection:'row',justifyContent:'space-between',alignItems:'flex-start',gap:12},
  symbol:{color:C.text,fontSize:21,fontWeight:'800'},name:{color:C.muted,fontSize:12,marginTop:2,maxWidth:210},
  pill:{borderWidth:1,borderRadius:999,paddingHorizontal:10,paddingVertical:5},pillText:{fontSize:11,fontWeight:'800'},
  priceRow:{flexDirection:'row',justifyContent:'space-between',marginTop:14},price:{color:C.text,fontSize:18,fontWeight:'700'},level:{color:C.cyan,fontSize:12,fontWeight:'700',maxWidth:'50%',textAlign:'right'},
  scores:{flexDirection:'row',gap:8,marginTop:14},score:{flex:1,backgroundColor:C.panel2,borderRadius:12,padding:10},scoreLabel:{color:C.muted,fontSize:10},scoreValue:{color:C.text,fontSize:18,fontWeight:'800',marginTop:2},
  metaRow:{flexDirection:'row',justifyContent:'space-between',marginTop:12},meta:{color:C.muted,fontSize:11},suggest:{color:C.green,fontSize:12,fontWeight:'700',marginTop:10},
  section:{color:C.text,fontSize:18,fontWeight:'800',marginBottom:12,marginTop:8}
});
