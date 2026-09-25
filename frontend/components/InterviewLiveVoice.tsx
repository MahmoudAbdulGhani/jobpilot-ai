'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from '../lib/api';
import type {Interview} from '../lib/interviews';

type Turn={question:string;answer:string};
type Options={available:boolean;max_minutes:number};
type Token={value:string;model:string;max_minutes:number;question_count:number};
type Event={type:string;transcript?:string;delta?:string};

export function InterviewLiveVoice({id,saved,onConfirmed,onBusy}:{id:string;saved?:Interview['live_voice'];onConfirmed:(value:Interview)=>void;onBusy:(value:boolean)=>void}){
  const [options,setOptions]=useState<Options|null>(null),[consent,setConsent]=useState(false),[status,setStatus]=useState('idle');
  const [error,setError]=useState(''),[caption,setCaption]=useState(''),[turns,setTurns]=useState<Turn[]>([]),[muted,setMuted]=useState(false);
  const pc=useRef<RTCPeerConnection|null>(null),stream=useRef<MediaStream|null>(null),audio=useRef<HTMLAudioElement|null>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const limit=useRef(6),open=useRef(false);
  const stop=useCallback(()=>{open.current=false;if(timer.current)clearTimeout(timer.current);timer.current=null;stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;pc.current?.close();pc.current=null;if(audio.current){audio.current.pause();audio.current.srcObject=null;}setStatus(previous=>previous==='live'||previous==='connecting'?'review':previous);onBusy(false);},[onBusy]);
  useEffect(()=>{let mounted=true;api<Options>(`/interviews/${id}/live-voice/options`).then(value=>{if(mounted)setOptions(value);}).catch(()=>{if(mounted)setOptions({available:false,max_minutes:10});});return()=>{mounted=false;stop();};},[id,stop]);
  useEffect(()=>{onBusy(status==='connecting'||status==='live'||status==='confirming');},[status,onBusy]);
  function onEvent(event:Event){
    if(event.type==='response.output_audio_transcript.delta'||event.type==='conversation.item.input_audio_transcription.delta')setCaption(previous=>(previous+String(event.delta||'')).slice(-1200));
    if(event.type==='response.output_audio_transcript.done'&&event.transcript?.trim()){
      setCaption('');setTurns(previous=>previous.length>=limit.current?previous:[...previous,{question:event.transcript!.trim().slice(0,1000),answer:''}]);
    }
    if(event.type==='conversation.item.input_audio_transcription.completed'&&event.transcript?.trim()){
      setCaption('');setTurns(previous=>{const copy=[...previous];const index=copy.findIndex(turn=>!turn.answer);if(index>=0)copy[index]={...copy[index],answer:event.transcript!.trim().slice(0,3000)};return copy;});
    }
    if(event.type==='error')setError('The live connection reported an error. Stop and review any captured transcript.');
  }
  async function start(){if(!options?.available||!consent||status!=='idle')return;setStatus('connecting');setError('');setTurns([]);setCaption('');try{
      const local=await navigator.mediaDevices.getUserMedia({audio:true});stream.current=local;
      const token=await api<Token>(`/interviews/${id}/live-voice/token`,{method:'POST'},false);limit.current=token.question_count;
      const peer=new RTCPeerConnection();pc.current=peer;local.getTracks().forEach(track=>peer.addTrack(track,local));
      const player=new Audio();player.autoplay=true;audio.current=player;peer.ontrack=event=>{player.srcObject=event.streams[0];};
      const channel=peer.createDataChannel('oai-events');channel.onmessage=message=>{try{onEvent(JSON.parse(String(message.data)) as Event);}catch{setError('A caption event could not be read.');}};
      channel.onopen=()=>{open.current=true;channel.send(JSON.stringify({type:'response.create'}));};
      const offer=await peer.createOffer();await peer.setLocalDescription(offer);
      const reply=await fetch('https://api.openai.com/v1/realtime/calls',{method:'POST',body:offer.sdp,headers:{Authorization:`Bearer ${token.value}`,'Content-Type':'application/sdp'}});
      if(!reply.ok)throw new Error('Could not establish the live audio connection.');
      await peer.setRemoteDescription({type:'answer',sdp:await reply.text()});
      timer.current=setTimeout(()=>stop(),token.max_minutes*60_000);setStatus('live');
    }catch{stop();setStatus('review');setError('Live voice could not start. Your text interview is still available. No automatic retry.');}}
  async function confirm(){const reviewed=turns.filter(turn=>turn.question.trim()&&turn.answer.trim());if(reviewed.length<2)return;setStatus('confirming');setError('');try{const result=await api<Interview>(`/interviews/${id}/live-voice/confirm`,{method:'POST',body:JSON.stringify({confirm:true,turns:reviewed})},false);onConfirmed(result);setStatus('confirmed');}catch(caught){setStatus('review');setError((caught as Error).message);}}
  if(saved?.confirmed_turns&&saved.status==='feedback_failed')return <section className="interview-question"><h2>Confirmed live voice transcript</h2><p role="alert">Feedback failed validation. Your confirmed answers are saved; no automatic retry was sent.</p>{saved.confirmed_turns.map((turn,index)=><article key={index}><h3>Question {index+1}</h3><p>{turn.question}</p><p>{turn.answer}</p></article>)}</section>;
  if(!options?.available||saved)return null;
  return <section className="interview-question" aria-label="Live voice interview"><h2>Live voice interview</h2><p>Talk with the AI interviewer in real time. You can interrupt its speech, mute your microphone, or stop at any time. Captions are drafts; review each answer before saving or requesting feedback.</p>
    {status==='idle'&&<><label><input type="checkbox" checked={consent} onChange={event=>setConsent(event.target.checked)}/>I agree to send live microphone audio and the reviewed interview source to OpenAI.</label><button className="secondary-button" disabled={!consent} onClick={()=>void start()}>Start live conversation</button></>}
    {(status==='connecting'||status==='live')&&<><p role="status">{status==='connecting'?'Connecting…':'Live conversation active'}</p><p aria-live="polite">{caption}</p><button onClick={()=>{const next=!muted;stream.current?.getAudioTracks().forEach(track=>{track.enabled=!next;});setMuted(next);}}>{muted?'Unmute microphone':'Mute microphone'}</button><button onClick={stop}>Stop and review transcript</button></>}
    {error&&<p role="alert">{error}</p>}
    {(status==='review'||status==='confirming')&&<><h3>Review transcript before saving</h3>{turns.map((turn,index)=><div key={index}><label>Question {index+1}<textarea value={turn.question} maxLength={1000} onChange={event=>setTurns(previous=>previous.map((item,i)=>i===index?{...item,question:event.target.value}:item))}/></label><label>Your answer {index+1}<textarea value={turn.answer} maxLength={3000} onChange={event=>setTurns(previous=>previous.map((item,i)=>i===index?{...item,answer:event.target.value}:item))}/></label></div>)}<p>Only confirmed text will be saved. Feedback uses the existing interview rubric and may consume one AI request.</p><button className="primary-button" disabled={status==='confirming'||turns.filter(turn=>turn.question.trim()&&turn.answer.trim()).length<2} onClick={()=>void confirm()}>Confirm transcript and get feedback</button></>}
  </section>;
}
