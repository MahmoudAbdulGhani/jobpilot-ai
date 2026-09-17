// Isolate the feature widget; entitlement enforcement has dedicated connected tests.
vi.mock('../components/MeteredButton',()=>({MeteredButton:'button'}));
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {InterviewVoice} from '../components/InterviewVoice';
import {pcmWav} from '../lib/voice-recorder';
const {apiMock,recordMock}=vi.hoisted(()=>({apiMock:vi.fn(),recordMock:vi.fn()}));
vi.mock('../lib/api',()=>({api:apiMock}));
vi.mock('../lib/voice-recorder',async original=>({...await original<object>(),startRecording:recordMock}));
const options={available:true,provider:'deterministic-test',transcription_model:'whisper-1',speech_model:'tts-1',max_seconds:60,transcript_minutes:10};

describe('optional interview voice',()=>{
  beforeEach(()=>{
    apiMock.mockReset();recordMock.mockReset();apiMock.mockResolvedValue(options);
    URL.createObjectURL=vi.fn(()=> 'blob:synthetic');URL.revokeObjectURL=vi.fn();
    vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  });
  async function enable(){fireEvent.click(screen.getByLabelText('Use optional voice controls'));await screen.findByRole('button',{name:'Start recording'});}
  it('never requests microphone permission or speech on mount or enabling controls',async()=>{
    render(<InterviewVoice id="s" question={1} disabled={false} onTranscript={vi.fn()} onBusy={vi.fn()}/>);
    expect(apiMock).not.toHaveBeenCalled();expect(recordMock).not.toHaveBeenCalled();await enable();
    expect(recordMock).not.toHaveBeenCalled();expect(apiMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button',{name:'Generate spoken question'}).hasAttribute('disabled')).toBe(true);
  });
  it('records explicitly, requires consent and reviews an editable transcript without submitting',async()=>{
    const use=vi.fn(),stop=vi.fn(()=>new Blob(['synthetic']));recordMock.mockResolvedValue({stop,cancel:vi.fn()});
    apiMock.mockImplementation((path:string)=>Promise.resolve(path.endsWith('/options')?options:{status:'succeeded',transcript:'A draft transcript'}));
    render(<InterviewVoice id="s" question={1} disabled={false} onTranscript={use} onBusy={vi.fn()}/>);await enable();
    fireEvent.click(screen.getByRole('button',{name:'Start recording'}));
    await screen.findByText(/Recording microphone/);expect(recordMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Stop recording'}));expect(stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button',{name:'Send recording for transcription'}).hasAttribute('disabled')).toBe(true);
    fireEvent.click(screen.getByLabelText(/I agree to the described/));fireEvent.click(screen.getByRole('button',{name:'Send recording for transcription'}));
    const draft=await screen.findByLabelText('Review transcript');expect(use).not.toHaveBeenCalled();
    fireEvent.change(draft,{target:{value:''}});expect(screen.getByLabelText('Review transcript')).not.toBeNull();
    expect(screen.getByRole('button',{name:'Use reviewed transcript as answer draft'}).hasAttribute('disabled')).toBe(true);
    fireEvent.change(draft,{target:{value:'Reviewed accurate answer'}});fireEvent.click(screen.getByRole('button',{name:'Use reviewed transcript as answer draft'}));
    expect(use).toHaveBeenCalledWith('Reviewed accurate answer');
    expect(apiMock.mock.calls).toHaveLength(2);expect(apiMock.mock.calls[1][2]).toBe(false);
    expect(apiMock.mock.calls.every(c=>!c[0].endsWith('/advance')&&!c[0].endsWith('/answer'))).toBe(true);
  });
  it('permission denial leaves text alone and does not send audio',async()=>{
    const use=vi.fn();recordMock.mockRejectedValue(new Error('denied'));
    render(<InterviewVoice id="s" question={1} disabled={false} onTranscript={use} onBusy={vi.fn()}/>);await enable();
    fireEvent.click(screen.getByRole('button',{name:'Start recording'}));expect(await screen.findByRole('alert')).not.toBeNull();
    expect(use).not.toHaveBeenCalled();expect(apiMock).toHaveBeenCalledTimes(1);
  });
  it('allows cancellation while microphone permission is pending',async()=>{
    recordMock.mockImplementation((_seconds,_ended,signal:AbortSignal)=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('cancelled')))));
    render(<InterviewVoice id="s" question={1} disabled={false} onTranscript={vi.fn()} onBusy={vi.fn()}/>);await enable();
    fireEvent.click(screen.getByRole('button',{name:'Start recording'}));
    fireEvent.click(screen.getByRole('button',{name:'Cancel recording / clear draft'}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Start recording'}).hasAttribute('disabled')).toBe(false));
    expect(recordMock.mock.calls[0][2].aborted).toBe(true);expect(apiMock).toHaveBeenCalledTimes(1);
  });
  it('cancels on hide and unmount; revokes local playback URLs',async()=>{
    const cancel=vi.fn();recordMock.mockResolvedValue({stop:()=>new Blob(['x']),cancel});
    const {unmount}=render(<InterviewVoice id="s" question={1} disabled={false} onTranscript={vi.fn()} onBusy={vi.fn()}/>);await enable();
    fireEvent.click(screen.getByRole('button',{name:'Start recording'}));await screen.findByText(/Recording microphone/);
    Object.defineProperty(document,'hidden',{configurable:true,value:true});fireEvent(document,new Event('visibilitychange'));
    expect(cancel).toHaveBeenCalledTimes(1);expect(screen.queryByText(/Recording microphone/)).toBeNull();
    Object.defineProperty(document,'hidden',{configurable:true,value:false});
    fireEvent.click(screen.getByRole('button',{name:'Start recording'}));await screen.findByText(/Recording microphone/);
    fireEvent.click(screen.getByRole('button',{name:'Stop recording'}));unmount();expect(URL.revokeObjectURL).toHaveBeenCalled();
  });
  it('uses the same request key after a network failure and preserves text',async()=>{
    const use=vi.fn();recordMock.mockResolvedValue({stop:()=>new Blob(['x']),cancel:vi.fn()});
    apiMock.mockImplementation((p:string)=>p.endsWith('/options')?Promise.resolve(options):Promise.reject(new Error('Unavailable')));
    render(<InterviewVoice id="s" question={1} disabled={false} onTranscript={use} onBusy={vi.fn()}/>);await enable();
    fireEvent.click(screen.getByRole('button',{name:'Start recording'}));await screen.findByText(/Recording microphone/);
    fireEvent.click(screen.getByRole('button',{name:'Stop recording'}));fireEvent.click(screen.getByLabelText(/I agree/));
    fireEvent.click(screen.getByRole('button',{name:'Send recording for transcription'}));await screen.findByRole('alert');
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send recording for transcription'}).hasAttribute('disabled')).toBe(false));
    expect(apiMock).toHaveBeenCalledTimes(2);fireEvent.click(screen.getByRole('button',{name:'Send recording for transcription'}));
    await waitFor(()=>expect(apiMock).toHaveBeenCalledTimes(3));expect(apiMock.mock.calls[1][0]).toBe(apiMock.mock.calls[2][0]);expect(use).not.toHaveBeenCalled();
  });
  it('labels generated speech and provides stop/mute without autoplay',async()=>{
    apiMock.mockImplementation((p:string)=>Promise.resolve(p.endsWith('/options')?options:{status:'succeeded',audio:btoa('audio'),media_type:'audio/wav'}));
    render(<InterviewVoice id="s" question={1} disabled={false} onTranscript={vi.fn()} onBusy={vi.fn()}/>);await enable();
    fireEvent.click(screen.getByLabelText(/I agree/));fireEvent.click(screen.getByRole('button',{name:'Generate spoken question'}));
    const audio=await screen.findByLabelText('AI-generated question playback') as HTMLAudioElement;expect(audio.autoplay).toBe(false);
    fireEvent.click(screen.getByLabelText('Mute generated speech'));expect(audio.muted).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Stop spoken question'}));expect(audio.pause).toHaveBeenCalled();
    fireEvent.error(audio);expect(screen.getByRole('alert').textContent).toContain('no new request');expect(apiMock).toHaveBeenCalledTimes(2);
  });
  it('encodes bounded canonical WAV size and type',()=>{
    const result=pcmWav(new Float32Array(48000),48000);expect(result.size).toBe(32044);expect(result.type).toBe('audio/wav');
  });
});
