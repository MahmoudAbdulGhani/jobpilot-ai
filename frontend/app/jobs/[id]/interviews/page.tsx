'use client';
import {useParams} from 'next/navigation';
import {Shell} from '../../../../components/Shell';
import {InterviewHome} from '../../../../components/InterviewPractice';
export default function Page(){const {id}=useParams<{id:string}>();return <Shell><InterviewHome jobId={id}/></Shell>;}
