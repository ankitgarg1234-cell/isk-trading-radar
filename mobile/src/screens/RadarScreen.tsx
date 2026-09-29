import React,{useMemo,useState} from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { C } from '../theme';
import { CandidateCard, Pill } from '../components';
import type { Bootstrap } from '../types';

const FILTERS=['ALL','STRONG BUY','BUY','STARTER BUY','CONSIDER BUY','OWNED'];
export default function RadarScreen({data,refreshing,onRefresh,onOpenStock}:{data:Bootstrap;refreshing:boolean;onRefresh:()=>void;onOpenStock:(s:string)=>void}){
  const [q,setQ]=useState(''); const [filter,setFilter]=useState('ALL');
  const rows=useMemo(()=>data.candidates.filter(c=>{const matches=!q||`${c.symbol} ${c.name||''}`.toLowerCase().includes(q.toLowerCase());const f=filter==='ALL'||(filter==='OWNED'?c.owned:c.system_signal===filter);return matches&&f;}),[data.candidates,q,filter]);
  return <ScrollView style={s.wrap} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.green}/>}>
    <Text style={s.title}>Market Radar</Text><Text style={s.sub}>Decision-first view across the scanned US universe.</Text>
    <TextInput value={q} onChangeText={setQ} placeholder="Search ticker or company" placeholderTextColor={C.muted} style={s.search}/>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.filters}>{FILTERS.map(f=><Pressable key={f} onPress={()=>setFilter(f)}><Pill text={f} tone={filter===f?C.cyan:C.border}/></Pressable>)}</ScrollView>
    <Text style={s.count}>{rows.length} shown</Text>
    {rows.map(c=><CandidateCard key={c.symbol} c={c} onPress={()=>onOpenStock(c.symbol)}/>)}
  </ScrollView>
}
const s=StyleSheet.create({wrap:{flex:1,backgroundColor:C.bg},content:{padding:16,paddingBottom:120},title:{color:C.text,fontSize:28,fontWeight:'900',marginTop:8},sub:{color:C.muted,fontSize:13,marginTop:5},search:{backgroundColor:C.panel,color:C.text,borderRadius:14,borderWidth:1,borderColor:C.border,padding:13,marginTop:18},filters:{gap:8,paddingVertical:14},count:{color:C.muted,fontSize:11,marginBottom:10}});
