export type RuntimeStorage={schema_version:'runtime-storage/1';complete:boolean;allocated_bytes:number;warnings:string[];deletion_approved:false;categories:{name:string;allocated_bytes:number;logical_bytes:number;files:number;links_skipped:number}[]};
const count=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
export function formatRuntimeBytes(bytes:number):string{
 if(!count(bytes))throw Error('Invalid byte count');
 if(bytes<1024)return bytes+' B';
 if(bytes<1024**2)return (bytes/1024).toFixed(2)+' KiB';
 if(bytes<1024**3)return (bytes/1024**2).toFixed(2)+' MiB';
 return (bytes/1024**3).toFixed(2)+' GiB';
}
export function parseRuntimeStorage(value:unknown):RuntimeStorage{
 if(!value||typeof value!=='object')throw Error('无效的运行目录盘点');
 const d=value as Record<string,unknown>;
 if(d.schema_version!=='runtime-storage/1'||d.ok!==true||typeof d.complete!=='boolean'||d.deletion_approved!==false||!count(d.allocated_bytes)||!Array.isArray(d.warnings)||!d.warnings.every(v=>typeof v==='string')||!Array.isArray(d.categories))throw Error('运行目录盘点协议不匹配');
 const names=new Set<string>();let sum=0;
 for(const row of d.categories){
  if(!row||typeof row!=='object'||typeof row.name!=='string'||!row.name||names.has(row.name)||!['allocated_bytes','logical_bytes','files','links_skipped'].every(k=>count(row[k])))throw Error('无效的目录占用条目');
  names.add(row.name);sum+=row.allocated_bytes;
 }
 if(!Number.isSafeInteger(sum)||sum!==d.allocated_bytes||(d.complete&&d.warnings.length))throw Error('盘点汇总与明细不一致');
 return d as unknown as RuntimeStorage;
}
