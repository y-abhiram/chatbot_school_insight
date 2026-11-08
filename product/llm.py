import json,os
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from product.providers import select_provider,models_for,provider_status

def structured(provider,model,schema,prompt,question,history=None,on_delta=None):
    if provider=='gemini':
        llm=ChatGoogleGenerativeAI(model=model,google_api_key=os.environ['GEMINI_API_KEY'],timeout=45,max_retries=0)
        runnable=llm.with_structured_output(schema.model_json_schema() if on_delta else schema,method='json_schema')
    else:
        llm=ChatOpenAI(model=model,api_key=os.environ[provider.upper()+'_API_KEY'],base_url='https://api.openai.com/v1' if provider=='openai' else 'https://api.groq.com/openai/v1',timeout=45,max_retries=0,**({'use_responses_api':True,'store':False} if provider=='openai' else {}))
        runnable=llm.with_structured_output(schema.model_json_schema() if on_delta else schema,method='json_schema' if provider=='openai' else 'json_mode',**({'strict':True} if provider=='openai' else {}))
    messages=[SystemMessage(content=prompt+'\nReturn JSON matching: '+json.dumps(schema.model_json_schema()))]
    for item in (history or [])[-6:]:
        if not item['content'].strip():
            continue
        messages.append((HumanMessage if item['role']=='user' else AIMessage)(content=item['content'][:2500]))
    messages.append(HumanMessage(content=question))
    if on_delta:
        result={};previous=''
        # LangChain's JSON parser emits partial objects as provider tokens arrive.
        for partial in runnable.stream(messages):
            if not isinstance(partial,dict):continue
            result=partial
            value=partial.get('answer','')
            kind=partial.get('kind')
            if schema.__name__=='Intent' and kind not in ('answer','clarification'):continue
            if isinstance(value,str) and value.startswith(previous):
                delta=value[len(previous):]
                if delta:on_delta(delta)
                previous=value
        return schema.model_validate(result)
    result=runnable.invoke(messages)
    return schema.model_validate(result)
