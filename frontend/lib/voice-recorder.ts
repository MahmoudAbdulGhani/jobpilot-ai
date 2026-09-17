// A deliberately narrow upload format: mono, 16 kHz, signed 16-bit PCM WAV.
// No browser persistence, MediaRecorder container parsing or temporary files.
export function pcmWav(samples: Float32Array, rate: number): Blob {
  const count=Math.floor(samples.length*16000/rate), buffer=new ArrayBuffer(44+count*2), view=new DataView(buffer);
  function ascii(at:number,text:string){for(let i=0;i<text.length;i++)view.setUint8(at+i,text.charCodeAt(i));}
  ascii(0,'RIFF');view.setUint32(4,36+count*2,true);ascii(8,'WAVE');ascii(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  ascii(36,'data');view.setUint32(40,count*2,true);
  for(let i=0;i<count;i++){
    const start=Math.floor(i*rate/16000),end=Math.max(start+1,Math.floor((i+1)*rate/16000));
    let sum=0;for(let j=start;j<end;j++)sum+=samples[j]||0;
    const value=Math.max(-1,Math.min(1,sum/(end-start)));view.setInt16(44+i*2,Math.round(value*(value<0?32768:32767)),true);
  }
  return new Blob([buffer],{type:'audio/wav'});
}

export type Recording={stop:()=>Blob;cancel:()=>void};
export async function startRecording(seconds:number,ended:()=>void,signal:AbortSignal):Promise<Recording>{
  if(!navigator.mediaDevices?.getUserMedia||!window.AudioContext)throw new Error('Recording is unavailable in this browser. Use the text answer.');
  // Called exclusively from the explicit Start recording button.
  const stream=await navigator.mediaDevices.getUserMedia({audio:true});
  if(signal.aborted){stream.getTracks().forEach(t=>t.stop());throw new Error('Recording cancelled.');}
  let context:AudioContext|null=null,source:MediaStreamAudioSourceNode|null=null,processor:ScriptProcessorNode|null=null,gain:GainNode|null=null;
  let chunks:Float32Array[]=[],total=0,closed=false,timer:ReturnType<typeof setTimeout>|undefined;
  function release(){
    if(closed)return;closed=true;clearTimeout(timer);signal.removeEventListener('abort',cancel);
    stream.getTracks().forEach(t=>{t.onended=null;t.stop();});
    if(processor){processor.onaudioprocess=null;processor.disconnect();}source?.disconnect();gain?.disconnect();void context?.close();
  }
  function cancel(){release();chunks=[];total=0;}
  signal.addEventListener('abort',cancel,{once:true});
  try{
    context=new AudioContext();const rate=context.sampleRate;
    source=context.createMediaStreamSource(stream);
    // ScriptProcessor remains the compatibility path here; processing is
    // bounded and stops on tab hiding/unmount. No worklet runs in the background.
    processor=context.createScriptProcessor(4096,1,1);gain=context.createGain();gain.gain.value=0;
    processor.onaudioprocess=e=>{
      const input=e.inputBuffer.getChannelData(0),remaining=Math.max(0,seconds*rate-total);
      if(remaining){const block=input.slice(0,remaining);chunks.push(block);total+=block.length;}
      if(total>=seconds*rate)ended();
    };
    stream.getTracks().forEach(t=>{t.onended=ended;});
    source.connect(processor);processor.connect(gain);gain.connect(context.destination);await context.resume();
    if(signal.aborted){cancel();throw new Error('Recording cancelled.');}
    timer=setTimeout(ended,seconds*1000);
    return {cancel,stop:()=>{release();const samples=new Float32Array(total);let at=0;for(const block of chunks){samples.set(block,at);at+=block.length;}chunks=[];total=0;return pcmWav(samples,rate);}};
  }catch(error){cancel();throw error;}
}
