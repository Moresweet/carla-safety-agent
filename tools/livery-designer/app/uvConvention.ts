// Unreal's FBX exporter writes (u, 1-v); fbx_mesh_to_json restores (u, v).
// These preview coordinates already use the same top-left image origin as
// bridge decode_texture. Never flip that source-UV path a second time.
export function textureUploadFlipY(useSourceUV:boolean){return !useSourceUV;}
export function sourceUVPixel(u:number,v:number,width:number,height:number):[number,number]{
 return [u*width,v*height];
}
export function fittedProjectionFrame(aspect:number,size:number){
 const available=size*.9,w=aspect>=1?available:available*aspect,h=aspect>=1?available/aspect:available;
 return {w,h,x:(size-w)/2,y:(size-h)/2};
}
