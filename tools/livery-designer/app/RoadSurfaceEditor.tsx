"use client";
import {RefObject} from "react";
import SurfaceTextureEditor from "./SurfaceTextureEditor";
export default function RoadSurfaceEditor(props:{image:HTMLImageElement|null;output:RefObject<HTMLCanvasElement|null>;onRender:()=>void}){return <SurfaceTextureEditor {...props} label="Selected road surface" note="Lane markings and curbs remain independent." baseColor="#3f4549"/>}
