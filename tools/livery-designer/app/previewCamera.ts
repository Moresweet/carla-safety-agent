// Column-major orthographic matrix. Fit the bounding sphere so orbiting a
// long car or a wide roof never clips it in a narrow preview card.
export function previewCamera(yaw:number,pitch:number,aspect:number,center:number[],radius:number){
 if(!Number.isFinite(aspect)||aspect<=0||!Number.isFinite(radius)||radius<=0)throw new Error('Invalid preview bounds');
 const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
 const s=.9*Math.min(1,aspect)/radius;
 const a=cy*s/aspect,b=-sy*s/aspect,d=sy*sp*s,e=cy*sp*s,f=cp*s;
 const g=sy*cp*s,h=cy*cp*s,i=-sp*s;
 const [x,y,z]=center;
 return new Float32Array([a,d,g,0,b,e,h,0,0,f,i,0,-a*x-b*y,-d*x-e*y-f*z,-g*x-h*y-i*z,1]);
}

export function previewBounds(vertices:number[]){
 if(!vertices.length||vertices.length%15||vertices.some(v=>!Number.isFinite(v)))throw new Error('Invalid preview mesh');
 const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
 for(let i=0;i<vertices.length;i+=5)for(let k=0;k<3;k++){min[k]=Math.min(min[k],vertices[i+k]);max[k]=Math.max(max[k],vertices[i+k])}
 const center=min.map((v,k)=>(v+max[k])/2);
 let radius=0;
 for(let i=0;i<vertices.length;i+=5)radius=Math.max(radius,Math.hypot(vertices[i]-center[0],vertices[i+1]-center[1],vertices[i+2]-center[2]));
 if(!radius)throw new Error('Empty preview geometry');
 return {center,radius};
}
