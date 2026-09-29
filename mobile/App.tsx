import React,{useEffect,useState} from 'react';
import { ActivityIndicator, AppState, Pressable, SafeAreaView, StatusBar, StyleSheet, Text, View } from 'react-native';
import LoginScreen from './src/screens/LoginScreen';
import AttentionScreen from './src/screens/AttentionScreen';
import RadarScreen from './src/screens/RadarScreen';
import PortfolioScreen from './src/screens/PortfolioScreen';
import CopilotScreen from './src/screens/CopilotScreen';
import StockDetailScreen from './src/screens/StockDetailScreen';
import { bootstrap, hasToken, logout } from './src/api';
import type { Bootstrap } from './src/types';
import { C } from './src/theme';

type Tab='ATTENTION'|'RADAR'|'PORTFOLIO'|'AI';
export default function App(){
 const [auth,setAuth]=useState<boolean|null>(null);const [data,setData]=useState<Bootstrap|null>(null);const [tab,setTab]=useState<Tab>('ATTENTION');const [selected,setSelected]=useState<string|null>(null);const [loading,setLoading]=useState(false);const [error,setError]=useState('');
 async function load(){setLoading(true);try{const d=await bootstrap();setData(d);setError('');}catch(e:any){if(String(e.message).includes('authentication')){await logout();setAuth(false);setData(null);}else setError(e.message||'Could not load Radar');}finally{setLoading(false);}}
 useEffect(()=>{hasToken().then(v=>setAuth(v));},[]);
 useEffect(()=>{if(auth)load();},[auth]);
 useEffect(()=>{if(!auth)return;const poll=Math.max(60,data?.poll_seconds||60)*1000;const t=setInterval(()=>{if(AppState.currentState==='active')load();},poll);return()=>clearInterval(t);},[auth,data?.poll_seconds]);
 if(auth===null)return <View style={s.center}><ActivityIndicator color={C.green}/></View>;
 if(!auth)return <LoginScreen onDone={()=>setAuth(true)}/>;
 if(selected)return <SafeAreaView style={s.safe}><StatusBar barStyle="light-content"/><StockDetailScreen symbol={selected} onBack={()=>setSelected(null)}/></SafeAreaView>;
 if(!data)return <View style={s.center}><ActivityIndicator color={C.green}/><Text style={s.loading}>{error||'Loading Radar…'}</Text>{error?<Pressable onPress={load}><Text style={s.retry}>Retry</Text></Pressable>:null}</View>;
 const common={data,refreshing:loading,onRefresh:load,onOpenStock:setSelected};
 return <SafeAreaView style={s.safe}><StatusBar barStyle="light-content"/>
   <View style={s.top}><Text style={s.brand}>ISK RADAR</Text><Pressable onPress={async()=>{await logout();setAuth(false);setData(null)}}><Text style={s.signout}>Sign out</Text></Pressable></View>
   <View style={s.body}>{tab==='ATTENTION'?<AttentionScreen {...common} onChanged={load}/>:tab==='RADAR'?<RadarScreen {...common}/>:tab==='PORTFOLIO'?<PortfolioScreen {...common} onChanged={load}/>:<CopilotScreen onChanged={load}/>}</View>
   {error?<View style={s.banner}><Text style={s.bannerText}>{error}</Text></View>:null}
   <View style={s.tabs}>{([['ATTENTION','⚡','Attention'],['RADAR','◎','Radar'],['PORTFOLIO','▦','Portfolio'],['AI','✦','AI']] as const).map(([key,icon,label])=><Pressable key={key} style={s.tab} onPress={()=>setTab(key)}><Text style={[s.icon,{color:tab===key?C.green:C.muted}]}>{icon}</Text><Text style={[s.tabText,{color:tab===key?C.text:C.muted}]}>{label}</Text></Pressable>)}</View>
 </SafeAreaView>;
}
const s=StyleSheet.create({safe:{flex:1,backgroundColor:C.bg},body:{flex:1},center:{flex:1,backgroundColor:C.bg,alignItems:'center',justifyContent:'center',padding:24},loading:{color:C.muted,marginTop:12},retry:{color:C.green,fontWeight:'800',marginTop:12},top:{height:48,paddingHorizontal:16,flexDirection:'row',alignItems:'center',justifyContent:'space-between',borderBottomWidth:1,borderBottomColor:C.border},brand:{color:C.text,fontSize:13,fontWeight:'900',letterSpacing:1.5},signout:{color:C.muted,fontSize:11},tabs:{height:70,flexDirection:'row',backgroundColor:C.panel,borderTopWidth:1,borderTopColor:C.border},tab:{flex:1,alignItems:'center',justifyContent:'center',gap:3},icon:{fontSize:18,fontWeight:'900'},tabText:{fontSize:10,fontWeight:'700'},banner:{position:'absolute',left:12,right:12,bottom:78,backgroundColor:'#3B1720',borderWidth:1,borderColor:C.red,borderRadius:12,padding:10},bannerText:{color:C.text,fontSize:11}});
