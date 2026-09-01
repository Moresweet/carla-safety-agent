"use client";
import {RefObject} from "react";
import SurfaceTextureEditor from "./SurfaceTextureEditor";
export default function PedestrianClothingEditor(props:{image:HTMLImageElement|null;output:RefObject<HTMLCanvasElement|null>;onRender:()=>void}){return <SurfaceTextureEditor {...props} label="walker.pedestrian.0001 clothing slot 14" note="Skin, hair and eyes remain independent." baseColor="#536273"/>}
