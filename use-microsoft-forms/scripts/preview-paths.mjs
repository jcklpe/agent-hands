import {validateSpec,fail} from './schema.mjs';
export function extremePath(spec,mode){
 validateSpec(spec);if(!['more','fewer'].includes(mode))fail('invalid_path','Use more or fewer for a preview path.');
 const positions=new Map(spec.questions.map((q,i)=>[q.id,i])),visited=[],choices=[];
 let index=0;
 while(index<spec.questions.length){
  const question=spec.questions[index];visited.push(index);
  if(question.type==='choice'){
   const options=question.options.map(option=>{const target=question.branches?.[option]??question.next??spec.questions[index+1]?.id??'end';return {option,targetIndex:target==='end'?spec.questions.length:positions.get(target)};});
   const selected=options.reduce((a,b)=>(mode==='more'?b.targetIndex<a.targetIndex:b.targetIndex>a.targetIndex)?b:a);
   if(selected.targetIndex<=index)fail('invalid_branch','Preview paths must move forward.');
   choices.push({index,...selected});index=selected.targetIndex;
  }else index++;
 }
 return {mode,visited,choices};
}
