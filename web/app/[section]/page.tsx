import { notFound } from 'next/navigation';
export default async function Page({params}:{params:Promise<{section:string}>}){const {section}=await params;if(!['chat','overview','sources','knowledge','schema','history','analytics','team','settings'].includes(section))notFound();return null;}
