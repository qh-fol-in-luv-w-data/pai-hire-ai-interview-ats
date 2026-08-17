export type JdSections={overview:string;responsibilities:string;requirements:string;benefits:string;other:string};
export const emptyJd=():JdSections=>({overview:'',responsibilities:'',requirements:'',benefits:'',other:''});

function sectionFromHeading(value:string):keyof JdSections|null{
  const heading=value.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  if(/tong quan|gioi thieu|mo ta chung|job overview|summary/.test(heading))return 'overview';
  if(/trach nhiem|cong viec|nhiem vu|job description|responsibilit/.test(heading))return 'responsibilities';
  if(/yeu cau|tieu chi|qualification|requirement|ky nang/.test(heading))return 'requirements';
  if(/quyen loi|phuc loi|benefit|che do/.test(heading))return 'benefits';
  if(/thong tin khac|dia diem|thoi gian|other|lien he/.test(heading))return 'other';
  return null;
}

export function parseJd(content:string):JdSections{
  const result=emptyJd(); let current:keyof JdSections='overview'; let recognized=false;
  for(const raw of (content||'').split('\n')){
    const line=raw.trim(); if(!line)continue;
    const cleanHeading=line.replace(/^#{1,6}\s*/,'').replace(/^\*\*(.+)\*\*$/,'$1').replace(/:$/,'').trim();
    const section=sectionFromHeading(cleanHeading);
    if(section&&(line.startsWith('#')||line.startsWith('**')||line.endsWith(':')||line===line.toUpperCase())){current=section;recognized=true;continue}
    const clean=line.replace(/^[-*•]\s*/,'').replace(/\*\*/g,'').trim();
    result[current]+=(result[current]?'\n':'')+clean;
  }
  if(!recognized&&!result.overview&&content.trim())result.overview=content.trim();
  return result;
}

const bullets=(value:string)=>value.split('\n').map(line=>line.trim().replace(/^[-*•]\s*/, '')).filter(Boolean).map(line=>`- ${line}`).join('\n');
export function composeJd(sections:JdSections):string{
  const blocks:string[]=[];
  if(sections.overview.trim())blocks.push(`## Tổng quan vị trí\n${sections.overview.trim()}`);
  if(sections.responsibilities.trim())blocks.push(`## Trách nhiệm công việc\n${bullets(sections.responsibilities)}`);
  if(sections.requirements.trim())blocks.push(`## Yêu cầu ứng viên\n${bullets(sections.requirements)}`);
  if(sections.benefits.trim())blocks.push(`## Quyền lợi\n${bullets(sections.benefits)}`);
  if(sections.other.trim())blocks.push(`## Thông tin khác\n${sections.other.trim()}`);
  return blocks.join('\n\n');
}
