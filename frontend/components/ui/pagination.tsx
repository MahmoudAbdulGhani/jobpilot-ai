import * as React from 'react';
import {CaretLeft,CaretRight} from '@phosphor-icons/react/dist/ssr';
import {Button} from '@/components/ui/button';
import {cn} from '@/lib/utils';

interface PaginationProps{
  page:number;
  total:number;
  pageSize:number;
  onPageChange:(page:number)=>void;
  ariaLabel?:string;
  className?:string;
}

function Pagination({page,total,pageSize,onPageChange,ariaLabel='Pagination',className}:PaginationProps){
  const totalPages=Math.max(1,Math.ceil(total/pageSize));
  const canPrev=page>1;
  const canNext=page<totalPages;
  return <nav aria-label={ariaLabel} className={cn('flex items-center justify-center gap-2',className)}>
    <Button variant="outline" size="sm" onClick={()=>onPageChange(page-1)} disabled={!canPrev} aria-label="Previous page"><CaretLeft aria-hidden="true"/><span className="hidden sm:inline">Previous</span></Button>
    <span className="px-2 text-sm text-muted-foreground" aria-live="polite">Page {page} of {totalPages}</span>
    <Button variant="outline" size="sm" onClick={()=>onPageChange(page+1)} disabled={!canNext} aria-label="Next page"><span className="hidden sm:inline">Next</span><CaretRight aria-hidden="true"/></Button>
  </nav>;
}

export {Pagination};
