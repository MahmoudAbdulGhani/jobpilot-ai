export type Config={provider:string;model:string;reasoning:string;max_output_tokens:number;max_calls?:number};
export type Source={job:{title:string;company:string;description:string};source_kind:string;source_name?:string;candidate_profile:Record<string,unknown>;cv_text:string;cover_letter_text?:string};
export type Preview={source_snapshot:Source;configuration:Config;preview_hash:string};
export type Options={available:boolean;message:string|null;configuration:Config;max_questions:number;resumes:{id:string;name:string}[];packs:{id:string;version:number;approved_at:string}[]};
export type Criterion={assessment:'demonstrated'|'needs_detail'|'insufficient_evidence';answer_quotes:string[];focus:string};
export type Turn={number:number;category:string;question:{strategy:string;source:string;quote:string};text:string;answer:string;feedback:Record<string,Criterion>|null};
export type Interview={id:string;job_id:string;status:string;revision:number;mode:string;question_count:number;configuration:Config;source_snapshot:Source;turns:Turn[];guidance:Record<string,string>;actions:Record<string,string>;practice_actions:string[];example_structures:Record<string,string>;practice_priorities:string[];operations:{id:string;step:number;status:string;outcome:string|null;usage:{input_tokens:number;output_tokens:number;reasoning_tokens:number|null}|null}[]};
export type History={items:{id:string;status:string;mode:string;question_count:number;created_at:string}[];next_cursor:string|null};
