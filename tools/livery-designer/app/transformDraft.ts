export const axes=['x','y','z','yaw'] as const;
export type TransformFields=Record<typeof axes[number],string>;
export type TransformItem={location:{x:number;y:number;z:number};rotation?:{yaw:number}};
export function transformFields(item:TransformItem):TransformFields{
 return {x:String(item.location.x),y:String(item.location.y),z:String(item.location.z),yaw:String(item.rotation?.yaw??0)};
}
export function parseTransformFields(fields:TransformFields){
 if(axes.some(key=>fields[key].trim()===''||!Number.isFinite(Number(fields[key]))))return null;
 return {location:{x:Number(fields.x),y:Number(fields.y),z:Number(fields.z)},rotation:{yaw:Number(fields.yaw)}};
}
