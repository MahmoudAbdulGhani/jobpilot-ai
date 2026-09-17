'use client';
import {useEffect,useRef,useState} from 'react';
import {api} from '../lib/api';
import {startRecording,type Recording} from '../lib/voice-recorder';

type Options={available:boolean;message?:string;provider:string;transcription_model:string;speech_model:string;max_seconds:number;transcript_minutes:number};
type Result={status:string;transcript:string|null;audio:string|null;media_type:string|null};
type Props={id:string;question:number;disabled:boolean;onTranscript:(text:string)=>void;onBusy:(busy:boolean)=>void};

export function InterviewVoice(props:Props){
  const [enabled,setEnabled]=useState(false);
  return <section className="mailbox-card"><label><input type="checkbox" checked={enabled} disabled={props.disabled} onChange={e=>setEnabled(e.target.checked)}/>Use optional voice controls</label>
    {enabled&&<VoiceControls {...props}/>}</section>;
}

function VoiceControls({id,question,disabled,onTranscript,onBusy}:Props){
  const [options,setOptions]=useState<Options|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[recording,setRecording]=useState(false),[pending,setPending]=useState(false),[consent,setConsent]=useState(false);
  const [clip,setClip]=useState<Blob|null>(null),[clipUrl,setClipUrl]=useState(''),[speechUrl,setSpeechUrl]=useState(''),[transcript,setTranscript]=useState(''),[muted,setMuted]=useState(false);
  const [acquiring,setAcquiring]=useState(false);
  const [hasTranscript,setHasTranscript]=useState(false);
  const recorder=useRef<Recording|null>(null),abort=useRef<AbortController|null>(null),mounted=useRef(true),busy=useRef(false),recordedAudio=useRef<HTMLAudioElement|null>(null),spokenAudio=useRef<HTMLAudioElement|null>(null);
  const transcribeKey=useRef<string|null>(null),speechKey=useRef<string|null>(null),urls=useRef<string[]>([]);
  function url(blob:Blob){const value=URL.createObjectURL(blob);urls.current.push(value);return value;}
  useEffect(()=>{mounted.current=true;const activeUrls=urls.current;let live=true;api<Options>(`/interviews/${id}/voice/options`).then(o=>{if(live)setOptions(o);}).catch(()=>{if(live)setError('Voice options are unavailable. Your text answer is unchanged.');});
    const hidden=()=>{if(document.hidden){abort.current?.abort();recorder.current?.cancel();recorder.current=null;setRecording(false);spokenAudio.current?.pause();recordedAudio.current?.pause();setNotice('Recording stopped when the page became hidden. Text is unchanged.');}};
    document.addEventListener('visibilitychange',hidden);
    return()=>{live=false;mounted.current=false;abort.current?.abort();recorder.current?.cancel();activeUrls.forEach(u=>URL.revokeObjectURL(u));document.removeEventListener('visibilitychange',hidden);onBusy(false);};
  },[id,onBusy]);
  useEffect(()=>{onBusy(recording||pending);},[recording,pending,onBusy]);
  function stop(){const active=recorder.current;if(!active)return;recorder.current=null;const blob=active.stop();setRecording(false);setClip(blob);setClipUrl(url(blob));transcribeKey.current=crypto.randomUUID();setNotice('Recording stopped. Play it back or cancel before sending.');}
  function clear(){abort.current?.abort();recorder.current?.cancel();recorder.current=null;recordedAudio.current?.pause();setRecording(false);setClip(null);if(clipUrl)URL.revokeObjectURL(clipUrl);setClipUrl('');transcribeKey.current=null;setTranscript('');setHasTranscript(false);setNotice('Recording and transcript draft cleared. Your text answer is unchanged.');}
  async function start(){if(busy.current||recording)return;busy.current=true;setPending(true);setAcquiring(true);setError('');clear();setNotice('');spokenAudio.current?.pause();abort.current=new AbortController();
    try{const active=await startRecording(options!.max_seconds,stop,abort.current.signal);if(!mounted.current||document.hidden){active.cancel();return;}recorder.current=active;setRecording(true);}
    catch{if(mounted.current)setError('Microphone access was denied, cancelled or interrupted. You can still type your answer.');}
    finally{busy.current=false;if(mounted.current){setPending(false);setAcquiring(false);}}
  }
  async function transcribe(){if(!clip||!consent||busy.current)return;busy.current=true;setPending(true);setError('');recordedAudio.current?.pause();
    try{const query=new URLSearchParams({request_key:transcribeKey.current!,question_number:String(question),consent:'true'});
      const result=await api<Result>(`/interviews/${id}/voice/transcribe?${query}`,{method:'POST',body:clip,headers:{'Content-Type':'audio/wav'}},false);
      if(!mounted.current)return;
      if(result.status!=='succeeded'||!result.transcript)throw new Error('Transcription is pending, failed or expired. No automatic retry. Your text answer is unchanged.');
      setTranscript(result.transcript);setHasTranscript(true);setNotice('Review and edit the transcript below. It has not been submitted as an answer.');
      setClip(null);if(clipUrl)URL.revokeObjectURL(clipUrl);setClipUrl('');
    }catch(e){if(mounted.current)setError((e as Error).message);}finally{busy.current=false;if(mounted.current)setPending(false);}
  }
  async function speak(){if(!consent||busy.current)return;busy.current=true;setPending(true);setError('');speechKey.current??=crypto.randomUUID();
    try{const result=await api<Result>(`/interviews/${id}/voice/speak`,{method:'POST',body:JSON.stringify({request_key:speechKey.current,question_number:question,consent:true})},false);
      if(!mounted.current)return;
      if(result.status!=='succeeded'||!result.audio)throw new Error('Speech is unavailable or was already generated. No automatic retry. Read the visible question.');
      const bytes=Uint8Array.from(atob(result.audio),c=>c.charCodeAt(0));setSpeechUrl(url(new Blob([bytes],{type:result.media_type||'audio/mpeg'})));
      setNotice('AI-generated question audio is ready. Press Play to listen.');
    }catch(e){if(mounted.current)setError((e as Error).message);}finally{busy.current=false;if(mounted.current)setPending(false);}
  }
  return <div>
    {!options&&!error&&<p role="status">Loading voice options…</p>}
    {options&&!options.available&&<p>{options.message}</p>}
    {options?.available&&<>
      <p>{options.provider} · transcription {options.transcription_model} · speech {options.speech_model}. {options.provider==='deterministic-test'?'Synthetic test audio only; no live speech provider.':''}</p>
      <p>Record up to {options.max_seconds} seconds. Nothing is sent while recording. Sending a recording shares its audio with this provider. Generating speech shares the visible question and its displayed excerpt, which may quote your previous answer. Each request consumes your account quota. No automatic retries or fallback.</p>
      <p>JobPilot does not store audio. Transcript drafts expire after {options.transcript_minutes} minutes; reviewed answers follow interview retention. Provider retention may differ. Feedback assesses submitted text only, never your voice, accent, emotion or personality.</p>
      <label><input type="checkbox" checked={consent} disabled={pending||recording} onChange={e=>setConsent(e.target.checked)}/>I agree to the described external audio and question processing.</label>
      <div><button type="button" disabled={disabled||pending||recording} onClick={()=>void start()}>Start recording</button>
      <button type="button" disabled={!recording} onClick={stop}>Stop recording</button>
      <button type="button" disabled={pending&&!acquiring} onClick={clear}>Cancel recording / clear draft</button></div>
      {recording&&<p role="status">● Recording microphone — stops at {options.max_seconds} seconds. Stop or cancel at any time.</p>}
      {clipUrl&&<audio aria-label="Recorded answer playback" ref={recordedAudio} src={clipUrl} controls onError={()=>setError('Recording playback failed. Cancel and use text, or explicitly record again.')}/>}
      {clip&&<button type="button" disabled={!consent||pending||disabled} onClick={()=>void transcribe()}>Send recording for transcription</button>}
      {hasTranscript&&<><label>Review transcript<textarea value={transcript} maxLength={3000} rows={5} onChange={e=>setTranscript(e.target.value)}/></label>
        <button type="button" disabled={disabled||pending||!transcript.trim()} onClick={()=>{onTranscript(transcript);setNotice('Reviewed transcript copied to your answer. Save or submit it using the text controls.');}}>Use reviewed transcript as answer draft</button></>}
      <p>Optional AI-generated speech. Visible question text remains available.</p>
      {!speechUrl&&<button type="button" disabled={!consent||disabled||pending||recording} onClick={()=>void speak()}>Generate spoken question</button>}
      {speechUrl&&<><audio aria-label="AI-generated question playback" ref={spokenAudio} src={speechUrl} controls muted={muted} onError={()=>setError('Speech playback failed. Read the visible question; no new request was sent.')}/>
      <button type="button" onClick={()=>{if(spokenAudio.current){spokenAudio.current.pause();spokenAudio.current.currentTime=0;}}}>Stop spoken question</button>
      <label><input type="checkbox" checked={muted} onChange={e=>setMuted(e.target.checked)}/>Mute generated speech</label></>}
    </>}
    {pending&&<p role="status">Voice action pending. Your text answer is unchanged.</p>}
    {notice&&<p role="status">{notice}</p>}{error&&<p role="alert" className="form-error">{error}</p>}
  </div>;
}
