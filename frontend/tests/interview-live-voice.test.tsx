import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {InterviewLiveVoice} from '../components/InterviewLiveVoice';

const {apiMock}=vi.hoisted(()=>({apiMock:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock}));

let channel:{onopen:(()=>void)|null;onmessage:((event:{data:string})=>void)|null;send:ReturnType<typeof vi.fn>};
let stopped:ReturnType<typeof vi.fn>;
class Peer{
  ontrack:((event:{streams:MediaStream[]})=>void)|null=null;
  localDescription:unknown=null;
  constructor(){channel={onopen:null,onmessage:null,send:vi.fn()};}
  addTrack=vi.fn();createDataChannel=()=>channel;
  createOffer=async()=>({type:'offer',sdp:'synthetic-sdp'});
  setLocalDescription=async(value:unknown)=>{this.localDescription=value;};
  setRemoteDescription=async()=>{};
  close=vi.fn();
}

describe('live voice interview',()=>{
  beforeEach(()=>{apiMock.mockReset();stopped=vi.fn();vi.stubGlobal('RTCPeerConnection',Peer);vi.stubGlobal('Audio',class{autoplay=false;srcObject=null;pause=vi.fn();});Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:vi.fn(async()=>({getTracks:()=>[{stop:stopped,enabled:true}],getAudioTracks:()=>[{stop:stopped,enabled:true}]}))}});vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,text:async()=>"synthetic-answer"})));});
  it('keeps the disabled mode hidden and makes no provider request',async()=>{apiMock.mockResolvedValueOnce({available:false,max_minutes:10});render(<InterviewLiveVoice id="session" onBusy={vi.fn()} onConfirmed={vi.fn()}/>);await waitFor(()=>expect(apiMock).toHaveBeenCalledTimes(1));expect(screen.queryByText('Live voice interview')).toBeNull();expect(fetch).not.toHaveBeenCalled();});
  it('reviews and confirms two conversational turns before saving feedback',async()=>{
    apiMock.mockImplementation(async(path:string)=>path.endsWith('/options')?{available:true,max_minutes:10}:path.endsWith('/token')?{value:'ephemeral-only',model:'gpt-realtime-2.1',max_minutes:10,question_count:2}:{id:'session',status:'completed'});
    const confirmed=vi.fn();render(<InterviewLiveVoice id="session" onBusy={vi.fn()} onConfirmed={confirmed}/>);
    expect(await screen.findByText('Live voice interview')).not.toBeNull();
    expect(screen.getByRole('button',{name:'Start live conversation'}).hasAttribute('disabled')).toBe(true);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByRole('button',{name:'Start live conversation'}));
    await screen.findByText('Live conversation active');
    await act(async()=>{channel.onopen?.();for(const [type,transcript] of [
      ['response.output_audio_transcript.done','Tell me about a relevant project.'],
      ['conversation.item.input_audio_transcription.completed','I built a booking API.'],
      ['response.output_audio_transcript.done','How did you validate it?'],
      ['conversation.item.input_audio_transcription.completed','I checked failure paths.']])channel.onmessage?.({data:JSON.stringify({type,transcript})});});
    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({type:'response.create'}));
    fireEvent.click(screen.getByRole('button',{name:'Stop and review transcript'}));
    const answers=screen.getAllByLabelText(/Your answer/);fireEvent.change(answers[1],{target:{value:'I tested timeout and error paths.'}});
    fireEvent.click(screen.getByRole('button',{name:'Confirm transcript and get feedback'}));
    await waitFor(()=>expect(confirmed).toHaveBeenCalledWith(expect.objectContaining({status:'completed'})));
    expect(apiMock).toHaveBeenCalledWith('/interviews/session/live-voice/confirm',expect.objectContaining({method:'POST'}),false);
    const body=JSON.parse(apiMock.mock.calls.find(call=>String(call[0]).endsWith('/confirm'))![1].body);
    expect(body.confirm).toBe(true);expect(body.turns).toHaveLength(2);expect(body.turns[1].answer).toBe('I tested timeout and error paths.');
    expect(stopped).toHaveBeenCalled();
  });
});
