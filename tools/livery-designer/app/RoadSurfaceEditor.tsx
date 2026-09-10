"use client";
import {RefObject} from "react";
import SurfaceTextureEditor from "./SurfaceTextureEditor";
export default function RoadSurfaceEditor(props:{image:HTMLImageElement|null;output:RefObject<HTMLCanvasElement|null>;onRender:()=>void}){return <SurfaceTextureEditor {...props} label="Road texture draft" note="纹理草稿不代表实际 UV；请在具体对象的材质槽编辑器核验。" baseColor="#3f4549"/>}
