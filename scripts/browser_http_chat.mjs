// Regression: public HTTP pages must send messages without crypto.randomUUID.
// Start the frontend image on 127.0.0.1:3091 before running this script.
// API fixtures avoid provider calls, credentials and changes to school records.
import {spawn} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const port=process.env.HTTP_CHAT_PORT||'3091';
const profile=await mkdtemp(path.join(os.tmpdir(),'schooliq-http-browser-'));
const browser=spawn(process.env.CHROMIUM_BIN||'/home/jony/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',[
  '--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-proxy-server',
  '--host-resolver-rules=MAP schooliq.test 127.0.0.1','--remote-debugging-port=9231',
  `--user-data-dir=${profile}`,'about:blank'
],{stdio:'ignore'});
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let socket,sequence=0,overviewRequests=0,historyRequests=0;const waiting=new Map(),errors=[],questions=[];
const cmd=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;waiting.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
const assert=(condition,label)=>{if(!condition)throw new Error(label);console.log('PASS:',label);};
try{
  let target;
  for(let i=0;i<100;i++){
    try{target=(await(await fetch('http://127.0.0.1:9231/json')).json()).find(item=>item.type==='page');if(target)break;}catch{}
    await pause(100);
  }
  if(!target)throw new Error('Chromium did not start');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  const identity={id:1,tenant_id:'school-demo',username:'http_test',name:'HTTP Test',role_name:'Student'};
  socket.addEventListener('message',async event=>{
    const message=JSON.parse(event.data);
    if(message.id){const pending=waiting.get(message.id);waiting.delete(message.id);if(pending)message.error?pending.reject(new Error(JSON.stringify(message.error))):pending.resolve(message.result);return;}
    if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text);
    if(message.method!=='Fetch.requestPaused')return;
    const {requestId,request}=message.params;
    const pathname=new URL(request.url).pathname;
    let body,contentType='application/json';
    if(pathname==='/api/chat/bootstrap')body=JSON.stringify({identity,greeting:'HTTP regression fixture',profile:null,scope:'Own records',can:['Read own records'],cannot:['Change records'],suggestions:['Show my attendance'],manual_pages:[15,18],read_only:true});
    else if(pathname==='/api/settings')body=JSON.stringify({providers:[{id:'gemini',name:'Gemini',configured:true,models:['fixture']}],default_provider:'gemini',default_model:'fixture'});
    else if(pathname==='/api/conversations')body='[]';
    else if(pathname==='/api/overview'){
      overviewRequests++;
      body=JSON.stringify({counts:{students:1,homework:1,v_pending_leaves:0},attendance_pct:[100,50,25,75][Math.min(overviewRequests-1,3)],scope:'Your own records',attendance:[],marks:[]});
    }else if(pathname==='/api/history'){
      historyRequests++;
      body=JSON.stringify([{id:'history-'+historyRequests,question:'History visit '+historyRequests,created_at:'2026-11-07T12:00:00Z',row_count:1,duration_ms:5,status:'success',sql_text:'SELECT fixture'}]);
      if(historyRequests===1)await pause(1200);
    }
    else if(pathname==='/api/chat/stream'){
      questions.push(JSON.parse(request.postData).question);
      const answer={message_id:'fixture-'+questions.length,conversation_id:'fixture-conversation',kind:'answer',answer:'HTTP request completed '+questions.length,report:null,documentation:null,source:'ASSISTANT',access_scope:'Student',provider:'gemini',model:'fixture'};
      body='event: result\ndata: '+JSON.stringify(answer)+'\n\n';contentType='text/event-stream';
    }else body='{}';
    try{await cmd('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:contentType}],body:Buffer.from(body).toString('base64')});}
    catch(error){if(pathname!=='/api/history')errors.push(error.message);}
  });
  const run=async expression=>{const result=await cmd('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(result.exceptionDetails.text);return result.result.value;};
  const until=async expression=>{for(let i=0;i<150;i++){if(await run(expression))return;await pause(100);}throw new Error('Timed out: '+expression);};
  await cmd('Runtime.enable');await cmd('Page.enable');
  await cmd('Fetch.enable',{patterns:[{urlPattern:'*/api/*',requestStage:'Request'}]});
  await cmd('Page.navigate',{url:`http://schooliq.test:${port}/chat`});
  await until("Boolean(document.querySelector('.welcome-prompts button'))");
  assert(await run('!window.isSecureContext'),'Regression runs in an actual insecure HTTP context');
  assert(await run("typeof crypto.randomUUID==='undefined'"),'HTTPS-only randomUUID is unavailable');
  await run("document.querySelector('.welcome-prompts button').click()");
  await until("document.querySelector('.chat-answer-text')?.textContent==='HTTP request completed 1'");
  assert(questions.length===1,'Suggested question reaches the streaming endpoint');
  assert(await run("document.querySelectorAll('.chat-user-message').length===1&&!document.querySelector('.chat-stop')"),'First message renders and busy state clears');
  await run("(()=>{const input=document.querySelector('#chat-question');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(input,'Show my marks');input.dispatchEvent(new Event('input',{bubbles:true}));})()");
  await pause(100);await run("document.querySelector('.chat-send').click()");
  await until("document.querySelectorAll('.chat-answer-text').length===2&&!document.querySelector('.chat-stop')");
  assert(questions.length===2,'Second message also completes on HTTP');
  assert(await run("document.querySelectorAll('.chat-user-message').length===2&&document.querySelectorAll('.chat-assistant-message').length===2"),'Message identifiers keep both conversations visible');
  const sidebar=async page=>{await run(`document.querySelector('.chat-sidebar a[href="/${page}"]').click()`);await until(`location.pathname==='/${page}'`);};
  await sidebar('overview');
  await until("document.querySelectorAll('.stat strong')[1]?.textContent==='100%'");
  assert(overviewRequests===1,'Overview fetches actual page data on entry');
  await sidebar('chat');
  await until("document.querySelectorAll('.chat-answer-text').length===2");
  assert(await run("document.querySelector('.chat-answer-text')?.textContent==='HTTP request completed 1'"),'Chat conversation survives switching sidebar pages');
  await sidebar('overview');
  await until("document.querySelectorAll('.stat strong')[1]?.textContent==='50%'");
  assert(overviewRequests===2,'Returning to overview refreshes changed server data');
  await sidebar('overview');
  await until("document.querySelectorAll('.stat strong')[1]?.textContent==='25%'");
  assert(overviewRequests===3,'Clicking the selected sidebar page refreshes it again');
  await sidebar('history');
  for(let i=0;i<30&&historyRequests===0;i++)await pause(50);
  assert(historyRequests===1,'Slow history request starts before navigation away');
  await sidebar('overview');
  await until("document.querySelectorAll('.stat strong')[1]?.textContent==='75%'");
  await pause(1400);
  assert(await run("document.querySelectorAll('.stat strong')[1]?.textContent==='75%'&&!document.querySelector('.history-row')"),'Late history response cannot overwrite the overview');
  await sidebar('history');
  await until("document.querySelector('.history-row strong')?.textContent==='History visit 2'");
  assert(historyRequests===2,'Returning to history fetches fresh results');
  await sidebar('chat');
  await until("document.querySelectorAll('.chat-answer-text').length===2");
  assert(await run("!document.querySelector('.chat-stop')"),'Sidebar navigation does not leave the chat busy');
  assert(errors.length===0,'No uncaught browser exceptions');
}finally{
  socket?.close();browser.kill();
  await new Promise(resolve=>browser.exitCode!==null?resolve():browser.once('exit',resolve));
  await rm(profile,{recursive:true,force:true});
}
