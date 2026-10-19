export type TemporalQuality = {
  sample_count:number; sampling_every_frames:number|null; temporal_order_valid:boolean;
  errors:{index:number;reason:string}[];
  unexpected_intervals:{from_frame:number;to_frame:number;frame_delta:number;time_delta_s:number}[];
  gap_check_available:boolean;
};

export default function ReplayQuality({quality}:{quality:TemporalQuality|null}) {
  if(!quality)return <p role="status">尚无可验证的同步索引；不能据此判断数据质量。</p>;
  return <section aria-label="回放索引质量" style={{fontSize:'1rem',padding:'12px 0'}}>
    <h3>回放索引检查</h3>
    <p>{quality.sample_count} 个样本 · {!quality.temporal_order_valid?'索引顺序异常，已暂停回放':quality.sample_count===0?'没有可回放样本，无法验证时序':quality.sample_count===1?'仅一个样本，无法验证递增关系':'帧号和时间戳严格递增'}</p>
    <p>{quality.sample_count<2?'样本不足，无法比较采样间隔。':quality.gap_check_available?`预期每 ${quality.sampling_every_frames} 帧保存一次；发现 ${quality.unexpected_intervals.length} 处间隔变化。`:'未记录采样间隔，无法检查间隔变化。'}</p>
    <p style={{fontSize:'14px'}}>间隔变化可能来自暂停录制或跳过采集，不等于传感器丢帧数量。此检查不验证原始图像、深度或点云文件。</p>
    {!!quality.errors.length&&<details><summary>查看 {quality.errors.length} 项索引错误</summary>
      <ul>{quality.errors.slice(0,20).map((error,index)=><li key={index}>样本位置 {error.index}：{error.reason}</li>)}</ul>
      {quality.errors.length>20&&<p>仅展示前 20 项。</p>}
    </details>}
    {!!quality.unexpected_intervals.length&&<details><summary>查看间隔变化</summary>
      <ul>{quality.unexpected_intervals.slice(0,20).map((gap,index)=><li key={index}>帧 {gap.from_frame} → {gap.to_frame}，间隔 {gap.frame_delta} 帧 / {gap.time_delta_s.toFixed(3)} 秒</li>)}</ul>
    </details>}
  </section>;
}
