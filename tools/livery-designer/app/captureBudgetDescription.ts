export function captureBudgetDescription(seconds:number,every:number):string{
 if(!Number.isInteger(seconds)||seconds<1||seconds>5000||!Number.isInteger(every)||every<1||every>100)
  return '采集时长或采样间隔无效';
 const requested=Math.ceil(seconds*20/every);
 return `录制上限 2000 帧；按 20 Hz 和每 ${every} 帧采样，本次约 ${requested} 个采样机会。`+
  (requested>2000?'所选时长超过录制帧数上限，后段不保证保存。':'')+
  '单次容量上限 20 GiB，剩余空间保护及其他配额可能使录制提前停止；实际保存量以回执为准。';
}
