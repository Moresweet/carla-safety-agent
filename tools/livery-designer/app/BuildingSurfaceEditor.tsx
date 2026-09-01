"use client";
import {RefObject} from "react";
import SurfaceTextureEditor from "./SurfaceTextureEditor";
export default function BuildingSurfaceEditor(props:{image:HTMLImageElement|null;output:RefObject<HTMLCanvasElement|null>;onRender:()=>void;label?:string;note?:string}){return <SurfaceTextureEditor {...props} label={props.label??"BP_House16 wall slot 0"} note={props.note??"Windows, roof and balcony remain independent."} baseColor="#c7b9a6"/>}
