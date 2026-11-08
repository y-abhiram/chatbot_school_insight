import type { Metadata } from 'next';
import './globals.css';
import {WorkspaceShell} from '@/components/workspace';
export const metadata:Metadata={title:'School Insight · Intelligence for education',description:'Secure school analytics and a grounded AI database assistant.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body><WorkspaceShell>{children}</WorkspaceShell></body></html>;}
