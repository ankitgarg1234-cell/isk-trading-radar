import React,{useState} from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { C } from '../theme';
import { login, API_URL } from '../api';

export default function LoginScreen({onDone}:{onDone:()=>void}){
  const [username,setUsername]=useState('admin'); const [password,setPassword]=useState(''); const [busy,setBusy]=useState(false); const [error,setError]=useState('');
  async function submit(){ if(!password){setError('Enter the dashboard password.');return;} setBusy(true);setError('');try{await login(username,password);onDone();}catch(e:any){setError(e.message||'Login failed');}finally{setBusy(false);} }
  return <KeyboardAvoidingView behavior={Platform.OS==='ios'?'padding':undefined} style={s.wrap}>
    <View style={s.card}><Text style={s.kicker}>PRIVATE TRADING SYSTEM</Text><Text style={s.title}>ISK Trading Radar</Text><Text style={s.sub}>One secure mobile client for iOS and Android.</Text>
      <TextInput autoCapitalize="none" value={username} onChangeText={setUsername} placeholder="Username" placeholderTextColor={C.muted} style={s.input}/>
      <TextInput secureTextEntry value={password} onChangeText={setPassword} placeholder="Password" placeholderTextColor={C.muted} style={s.input} onSubmitEditing={submit}/>
      {error?<Text style={s.error}>{error}</Text>:null}
      <Pressable onPress={submit} disabled={busy} style={s.button}>{busy?<ActivityIndicator color={C.bg}/>:<Text style={s.buttonText}>Sign in</Text>}</Pressable>
      <Text style={s.endpoint}>Backend: {API_URL}</Text>
    </View>
  </KeyboardAvoidingView>
}
const s=StyleSheet.create({wrap:{flex:1,backgroundColor:C.bg,justifyContent:'center',padding:22},card:{backgroundColor:C.panel,borderRadius:24,padding:22,borderWidth:1,borderColor:C.border},kicker:{color:C.cyan,fontSize:11,fontWeight:'800',letterSpacing:1.5},title:{color:C.text,fontSize:30,fontWeight:'900',marginTop:8},sub:{color:C.muted,fontSize:14,marginTop:8,marginBottom:20},input:{backgroundColor:C.panel2,color:C.text,borderRadius:14,paddingHorizontal:14,paddingVertical:14,marginTop:10,borderWidth:1,borderColor:C.border},button:{backgroundColor:C.green,borderRadius:14,padding:15,alignItems:'center',marginTop:16},buttonText:{color:C.bg,fontWeight:'900'},error:{color:C.red,marginTop:10},endpoint:{color:C.muted,fontSize:10,marginTop:16}});
