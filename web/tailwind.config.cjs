module.exports={future:{hoverOnlyWhenSupported:true},theme:{extend:{
colors:{bg:'#101418',pan:'#161b20',ln:'#263038',cu:'#1E1E1E',cn:'#2E2E2E',blue:'#42A5F5',green:'#66BB6A',red:'#FF5252',orange:'#FFA726',purple:'#9C27B0',lp:'#CE93D8',yellow:'#FFCA28',cyan:'#26C6DA',tx:'#ECEFF1',tx2:'#B0BEC5'},
fontFamily:{sans:['Tajawal','Segoe UI','Tahoma','system-ui','sans-serif'],mono:['JetBrains Mono','ui-monospace','monospace']},
transitionTimingFunction:{spring:'cubic-bezier(.34,1.56,.64,1)'},
keyframes:{
popIn:{'0%':{opacity:0,transform:'translateY(14px) scale(.95)'},'100%':{opacity:1,transform:'none'}},
rise:{'0%':{opacity:0,transform:'translateY(18px) scale(.98)',filter:'blur(8px)'},'100%':{opacity:1,transform:'none',filter:'none'}},
ignite:{'0%':{opacity:0,transform:'scale(.2)',filter:'blur(14px) brightness(2.5)'},'60%':{opacity:1,transform:'scale(1.07)',filter:'blur(0) brightness(1.35)'},'100%':{opacity:1,transform:'none',filter:'none'}},
drift:{to:{transform:'translate(4%,3%) scale(1.1)'}},
pulseRing:{'0%':{boxShadow:'0 0 0 0 rgba(255,82,82,.6)'},'100%':{boxShadow:'0 0 0 14px rgba(255,82,82,0)'}},
glow:{'0%,100%':{boxShadow:'0 0 18px -8px var(--mc)'},'50%':{boxShadow:'0 0 34px -4px var(--mc)'}},
bounceDot:{'0%,60%,100%':{transform:'none',opacity:.4},'30%':{transform:'translateY(-6px)',opacity:1}},
blink:{'50%':{opacity:0}},
shimmer:{to:{transform:'translateX(100%)'}},
eq:{'50%':{transform:'scaleY(.25)'}},
flash:{'0%,70%,100%':{transform:'none'},'78%':{transform:'scale(1.25) rotate(-10deg)'}},
beat:{'50%':{transform:'scale(1.18)'}}},
animation:{'pop-in':'popIn .5s cubic-bezier(.34,1.56,.64,1)',rise:'rise .9s cubic-bezier(.22,1,.36,1) both',ignite:'ignite 1.1s cubic-bezier(.22,1,.36,1) both',drift:'drift 18s ease-in-out infinite alternate','spin-slow':'spin 4s linear infinite','pulse-ring':'pulseRing 1.2s infinite',glow:'glow 1.6s ease-in-out infinite','bounce-dot':'bounceDot 1s ease-in-out infinite',blink:'blink 1s steps(2) infinite',shimmer:'shimmer 1.8s linear infinite',eq:'eq .9s ease-in-out infinite',flash:'flash 1.8s infinite',beat:'beat 1.6s ease-in-out infinite'}
}}}
module.exports.content=["./web/index.html"];
