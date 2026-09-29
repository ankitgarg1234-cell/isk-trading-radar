import React from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { C } from '../theme';
import { CandidateCard, Pill, SectionTitle, signalColor } from '../components';
import type { Bootstrap } from '../types';
import { ackAlert, snoozeAlert } from '../api';

export default function AttentionScreen({data,refreshing,onRefresh,onOpenStock,onChanged}:{data:Bootstrap;refreshing:boolean;onRefresh:()=>void;onOpenStock:(s:string)=>void;onChanged:()=>void}){
  const map=new Map(data.candidates.map(c=>[c.symbol,c]));
  async function ack(id:number){await ackAlert(id);onChanged();}
  async function snooze(id:number){await snoozeAlert(id,60);onChanged();}
  return <ScrollView style={s.wrap} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.green}/>}>
    <View style={s.hero}><View><Text style={s.kicker}>WHAT NEEDS ATTENTION NOW</Text><Text style={s.title}>{data.alerts.length} actionable item{data.alerts.length===1?'':'s'}</Text></View><Pill text={data.market_open?'MARKET OPEN':'MARKET CLOSED'} tone={data.market_open?C.green:C.muted}/></View>
    <View style={s.metrics}><View style={s.metric}><Text style={s.mLabel}>Portfolio risk</Text><Text style={s.mValue}>{Math.round(Number(data.account_risk?.score||0))}/100</Text></View><View style={s.metric}><Text style={s.mLabel}>Target</Text><Text style={s.mValue}>{data.risk_profile}</Text></View><View style={s.metric}><Text style={s.mLabel}>Universe</Text><Text style={s.mValue}>{data.universe_size||'—'}</Text></View></View>
    <SectionTitle>Action queue</SectionTitle>
    {data.alerts.length===0?<View style={s.empty}><Text style={s.emptyTitle}>Nothing requires action right now</Text><Text style={s.emptyText}>WAIT, WATCH and HOLD states remain in the Radar but stay out of this queue.</Text></View>:data.alerts.map(a=><View key={a.id} style={s.alert}>
      <Pressable onPress={()=>onOpenStock(a.symbol)}><View style={s.alertHead}><Text style={s.symbol}>{a.symbol}</Text><Pill text={a.action} tone={signalColor(a.action)}/></View><Text style={s.alertTitle}>{a.title}</Text><Text style={s.alertMsg}>{a.message}</Text></Pressable>
      <View style={s.actions}><Pressable onPress={()=>snooze(a.id)} style={s.secondary}><Text style={s.secondaryText}>Snooze 1h</Text></Pressable><Pressable onPress={()=>ack(a.id)} style={s.primary}><Text style={s.primaryText}>Acknowledge</Text></Pressable></View>
    </View>)}
    <SectionTitle>Top actionable setups</SectionTitle>
    {data.candidates.filter(c=>['STRONG BUY','BUY','STARTER BUY','CONSIDER BUY'].includes(c.system_signal)).slice(0,5).map(c=><CandidateCard key={c.symbol} c={c} onPress={()=>onOpenStock(c.symbol)}/>)}
  </ScrollView>
}
const s=StyleSheet.create({wrap:{flex:1,backgroundColor:C.bg},content:{padding:16,paddingBottom:120},hero:{flexDirection:'row',justifyContent:'space-between',alignItems:'flex-start',gap:12,marginTop:8},kicker:{color:C.cyan,fontSize:10,fontWeight:'900',letterSpacing:1.3},title:{color:C.text,fontSize:26,fontWeight:'900',marginTop:6},metrics:{flexDirection:'row',gap:8,marginVertical:18},metric:{flex:1,backgroundColor:C.panel,borderRadius:14,padding:12,borderWidth:1,borderColor:C.border},mLabel:{color:C.muted,fontSize:10},mValue:{color:C.text,fontSize:17,fontWeight:'800',marginTop:4},alert:{backgroundColor:C.panel,borderRadius:18,padding:16,borderWidth:1,borderColor:C.border,marginBottom:12},alertHead:{flexDirection:'row',justifyContent:'space-between'},symbol:{color:C.text,fontSize:20,fontWeight:'900'},alertTitle:{color:C.text,fontSize:15,fontWeight:'800',marginTop:12},alertMsg:{color:C.muted,fontSize:13,lineHeight:19,marginTop:5},actions:{flexDirection:'row',gap:8,marginTop:14},secondary:{flex:1,borderWidth:1,borderColor:C.border,borderRadius:12,padding:11,alignItems:'center'},primary:{flex:1,backgroundColor:C.panel2,borderRadius:12,padding:11,alignItems:'center'},secondaryText:{color:C.muted,fontWeight:'700',fontSize:12},primaryText:{color:C.green,fontWeight:'800',fontSize:12},empty:{backgroundColor:C.panel,padding:18,borderRadius:18,borderWidth:1,borderColor:C.border,marginBottom:16},emptyTitle:{color:C.text,fontWeight:'800'},emptyText:{color:C.muted,fontSize:13,lineHeight:19,marginTop:6}});
