"""guga 3D Desktop Pet -- transparent via color key, click to dance + toggle chat."""
import math, time, ctypes, socket
from pathlib import Path; from io import BytesIO
import glfw; from OpenGL.GL import *; import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parent; MODEL=ROOT/"gugugaga_3d"/"zmd_EM_vrm.vrm"
W,H=400,500
MAGENTA=(1.0,0.0,1.0,1.0)

VS="""#version 330 core
layout(location=0) in vec3 aPos;layout(location=1) in vec3 aNormal;layout(location=2) in vec2 aUV;
layout(location=3) in uvec4 aJoints;layout(location=4) in vec4 aWeights;
out vec3 vN;out vec3 vP;out vec2 vUV;
uniform mat4 uMVP;uniform mat4 uModel;uniform mat4 uBones[64];uniform bool uSkinned;
void main(){
    vec3 p=aPos,n=aNormal;
    if(uSkinned){
        mat4 b=uBones[aJoints.x]*aWeights.x+uBones[aJoints.y]*aWeights.y+uBones[aJoints.z]*aWeights.z+uBones[aJoints.w]*aWeights.w;
        p=(b*vec4(aPos,1)).xyz;n=mat3(b)*aNormal;
    }
    gl_Position=uMVP*vec4(p,1);vN=mat3(uModel)*n;vP=(uModel*vec4(p,1)).xyz;vUV=aUV;
}"""

FS_TEX="""#version 330 core
in vec3 vN;in vec3 vP;in vec2 vUV;out vec4 fc;
uniform sampler2D uTex;
void main(){vec3 L=normalize(vec3(2,3,4));float d=max(dot(normalize(vN),L),0);
vec3 c=texture(uTex,vUV).rgb*(vec3(0.35,0.38,0.45)+vec3(0.65,0.68,0.75)*d);
c*=0.7+0.3*(vP.y+0.5);fc=vec4(c,1);}"""

FS_FLAT="""#version 330 core
in vec3 vN;in vec3 vP;in vec2 vUV;out vec4 fc;
uniform vec3 uColor;
void main(){vec3 L=normalize(vec3(2,3,4));float d=max(dot(normalize(vN),L),0);
vec3 c=uColor*(vec3(0.35,0.38,0.45)+vec3(0.65,0.68,0.75)*d);
c*=0.7+0.3*(vP.y+0.5);fc=vec4(c,1);}"""

def mkprog(vs,fs):
    v=glCreateShader(GL_VERTEX_SHADER);glShaderSource(v,vs);glCompileShader(v)
    if not glGetShaderiv(v,GL_COMPILE_STATUS):raise RuntimeError(str(glGetShaderInfoLog(v)))
    f=glCreateShader(GL_FRAGMENT_SHADER);glShaderSource(f,fs);glCompileShader(f)
    if not glGetShaderiv(f,GL_COMPILE_STATUS):raise RuntimeError(str(glGetShaderInfoLog(f)))
    p=glCreateProgram();glAttachShader(p,v);glAttachShader(p,f);glLinkProgram(p)
    return p

def load_tex(blob,img,bvs):
    if img.bufferView is None:return 0
    bv=bvs[img.bufferView];off=bv.byteOffset or 0
    try:
        pi=Image.open(BytesIO(blob[off:off+bv.byteLength])).convert("RGBA");w,h=pi.size
        t=glGenTextures(1);glBindTexture(GL_TEXTURE_2D,t)
        glTexImage2D(GL_TEXTURE_2D,0,GL_SRGB8_ALPHA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,pi.tobytes())
        for p in[10241,10240,10242,10243]:glTexParameteri(GL_TEXTURE_2D,p,9729 if p<10242 else 10497)
        return t
    except:return 0

class Mesh:
    def __init__(s,v,n,u,idx,tid=0,c=(.7,.7,.75),jnt=None,wgt=None):
        s.v=v;s.n=n;s.u=u;s.idx=idx;s.tid=tid;s.col=c;s.jnt=jnt;s.wgt=wgt
        s.skinned=jnt is not None;s.vao=0;s.cnt=0

def up(m):
    m.vao=glGenVertexArrays(1);glBindVertexArray(m.vao)
    if m.skinned:
        j8=np.clip(m.jnt,0,255).astype('u1')
        N=len(m.v);buf=np.zeros(N*52,dtype='u1')
        vb=m.v.astype('f4').tobytes();nb=m.n.astype('f4').tobytes()
        ub=m.u.astype('f4').tobytes();jb=j8.tobytes();wb=m.wgt.astype('f4').tobytes()
        for i in range(N):
            o=i*52;buf[o:o+12]=np.frombuffer(vb[i*12:(i+1)*12],'u1')
            buf[o+12:o+24]=np.frombuffer(nb[i*12:(i+1)*12],'u1')
            buf[o+24:o+32]=np.frombuffer(ub[i*8:(i+1)*8],'u1')
            buf[o+32:o+36]=j8[i];buf[o+36:o+52]=np.frombuffer(wb[i*16:(i+1)*16],'u1')
        d=buf.tobytes()
        vb_=glGenBuffers(1);glBindBuffer(GL_ARRAY_BUFFER,vb_);glBufferData(GL_ARRAY_BUFFER,d,GL_STATIC_DRAW)
        S=52
        glVertexAttribPointer(0,3,GL_FLOAT,0,S,ctypes.c_void_p(0));glEnableVertexAttribArray(0)
        glVertexAttribPointer(1,3,GL_FLOAT,0,S,ctypes.c_void_p(12));glEnableVertexAttribArray(1)
        glVertexAttribPointer(2,2,GL_FLOAT,0,S,ctypes.c_void_p(24));glEnableVertexAttribArray(2)
        glVertexAttribIPointer(3,4,GL_UNSIGNED_BYTE,S,ctypes.c_void_p(32));glEnableVertexAttribArray(3)
        glVertexAttribPointer(4,4,GL_FLOAT,0,S,ctypes.c_void_p(36));glEnableVertexAttribArray(4)
    else:
        d=np.hstack([m.v,m.n,m.u]).flatten().astype('f4').tobytes()
        vb_=glGenBuffers(1);glBindBuffer(GL_ARRAY_BUFFER,vb_);glBufferData(GL_ARRAY_BUFFER,d,GL_STATIC_DRAW)
        S=32
        glVertexAttribPointer(0,3,GL_FLOAT,0,S,ctypes.c_void_p(0));glEnableVertexAttribArray(0)
        glVertexAttribPointer(1,3,GL_FLOAT,0,S,ctypes.c_void_p(12));glEnableVertexAttribArray(1)
        glVertexAttribPointer(2,2,GL_FLOAT,0,S,ctypes.c_void_p(24));glEnableVertexAttribArray(2)
    eb=glGenBuffers(1);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,eb)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER,m.idx.nbytes,m.idx,GL_STATIC_DRAW);m.cnt=len(m.idx)

def load(path):
    try:from pygltflib import GLTF2;gltf=GLTF2().load_binary(str(path))
    except:return None
    blob=gltf.binary_blob()
    if not blob:return None
    texs={}
    if gltf.textures and gltf.images:
        for i,t in enumerate(gltf.textures):
            if t.source is not None:
                tid=load_tex(blob,gltf.images[t.source],gltf.bufferViews)
                if tid:texs[i]=tid
    skin=gltf.skins[0] if gltf.skins else None
    ibm=None;joints=[]
    if skin:
        joints=skin.joints
        if skin.inverseBindMatrices is not None:
            ia=gltf.accessors[skin.inverseBindMatrices];iv=gltf.bufferViews[ia.bufferView]
            ibm=np.frombuffer(blob,'f4',ia.count*16,iv.byteOffset or 0).reshape(-1,4,4)
    parent_of={}
    for ni,n in enumerate(gltf.nodes):
        for c in (n.children or []):parent_of[c]=ni
    def depth(ni):
        d=0;cur=ni
        while cur in parent_of:cur=parent_of[cur];d+=1
        return d
    joint_depths={i:depth(joints[i]) for i in range(len(joints))}
    sorted_joints=sorted(range(len(joints)),key=lambda i:joint_depths[i])
    ms=[]
    for mesh in gltf.meshes:
        for pr in mesh.primitives:
            pa=gltf.accessors[pr.attributes.POSITION];pv=gltf.bufferViews[pa.bufferView]
            v=np.frombuffer(blob,'f4',pa.count*3,pv.byteOffset or 0).reshape(-1,3)
            nrm=pr.attributes.NORMAL
            n=np.frombuffer(blob,'f4',pa.count*3,(gltf.bufferViews[gltf.accessors[nrm].bufferView].byteOffset or 0)).reshape(-1,3) if nrm is not None else np.zeros((pa.count,3),'f4')
            uv=pr.attributes.TEXCOORD_0
            u=np.frombuffer(blob,'f4',pa.count*2,(gltf.bufferViews[gltf.accessors[uv].bufferView].byteOffset or 0)).reshape(-1,2) if uv is not None else np.zeros((pa.count,2),'f4')
            ia=pr.indices
            idx=np.frombuffer(blob,'u2' if gltf.accessors[ia].componentType==5123 else 'u4',gltf.accessors[ia].count,(gltf.bufferViews[gltf.accessors[ia].bufferView].byteOffset or 0)).astype('u4') if ia is not None else np.arange(pa.count,dtype='u4')
            jnt=None;wgt=None
            ja=pr.attributes.JOINTS_0;wa=pr.attributes.WEIGHTS_0
            if ja is not None and wa is not None:
                j_acc=gltf.accessors[ja];jv=gltf.bufferViews[j_acc.bufferView]
                dt='u1' if j_acc.componentType==5121 else 'u2'
                jnt=np.frombuffer(blob,dt,j_acc.count*4,jv.byteOffset or 0).reshape(-1,4).astype('u1')
                w_acc=gltf.accessors[wa];wv=gltf.bufferViews[w_acc.bufferView]
                wgt=np.frombuffer(blob,'f4',w_acc.count*4,wv.byteOffset or 0).reshape(-1,4)
            tid=0;col=(.7,.7,.75)
            if pr.material is not None and gltf.materials:
                mat=gltf.materials[pr.material];pbr=mat.pbrMetallicRoughness
                if pbr and pbr.baseColorTexture and pbr.baseColorTexture.index is not None:tid=texs.get(pbr.baseColorTexture.index,0)
                if pbr and pbr.baseColorFactor and not tid:col=tuple(pbr.baseColorFactor[:3])
            ms.append(Mesh(v,n,u,idx,tid,col,jnt,wgt))
    print(f"loaded {len(ms)} meshes, {len(texs)} tex, {len(joints)} bones")
    return ms,joints,ibm,parent_of,sorted_joints

def cube():
    v=.5;vt=np.array([-v,-v,v,v,-v,v,v,v,v,-v,v,v,v,-v,-v,-v,-v,-v,v,-v,v,v,-v,-v,v,v,v,v,v,v,-v,-v,v,-v,-v,-v,-v,v,-v,-v,-v,v,-v,v,-v,v,v,-v,v,-v,-v,-v,v,-v,v,-v,-v,v,v,-v,-v,-v,v,-v,-v],'f4')
    n=np.array([0,0,1]*4+[0,0,-1]*4+[0,1,0]*4+[0,-1,0]*4+[1,0,0]*4+[-1,0,0]*4,'f4')
    u=np.tile([[0,0],[0,1],[1,1],[0,0],[1,1],[1,0]],4).astype('f4')
    idx=np.arange(24,dtype='u4');m=Mesh(vt,n,u,idx,0,(.7,.3,.3));return[m],[],None,{},[]

def persp(f,a,nr,fr):
    x=1/math.tan(math.radians(f)/2);m=np.zeros((4,4),'f4')
    m[0,0]=x/a;m[1,1]=x;m[2,2]=(fr+nr)/(nr-fr);m[2,3]=2*fr*nr/(nr-fr);m[3,2]=-1;return m

def lookat(e,c,u):
    f=np.array(c)-np.array(e);f/=np.linalg.norm(f);s=np.cross(f,u);s/=np.linalg.norm(s);u=np.cross(s,f)
    m=np.identity(4,'f4');m[0,:3]=s;m[0,3]=-np.dot(s,e);m[1,:3]=u;m[1,3]=-np.dot(u,e)
    m[2,:3]=-f;m[2,3]=np.dot(f,e);return m

def ry(a):
    c=math.cos(a);s=math.sin(a);m=np.identity(4,'f4');m[0,0]=c;m[0,2]=s;m[2,0]=-s;m[2,2]=c;return m

def rot_axis(axis,angle):
    c=math.cos(angle);s=math.sin(angle);t=1-c;x,y,z=axis
    return np.array([[t*x*x+c,t*x*y-s*z,t*x*z+s*y,0],[t*x*y+s*z,t*y*y+c,t*y*z-s*x,0],[t*x*z-s*y,t*y*z+s*x,t*z*z+c,0],[0,0,0,1]],'f4')

def main():
    glfw.init()
    # NO TRANSPARENT_FRAMEBUFFER - use color key instead
    glfw.window_hint(glfw.DECORATED,0);glfw.window_hint(glfw.FLOATING,1)
    glfw.window_hint(glfw.DOUBLEBUFFER,1)
    w=glfw.create_window(W,H,"guga",None,None)
    if not w:glfw.terminate();return
    vm=glfw.get_video_mode(glfw.get_primary_monitor())
    glfw.set_window_pos(w,vm.size.width-W-30,vm.size.height-H-60)
    glfw.make_context_current(w);glfw.swap_interval(1)

    # Windows color-key transparency: make magenta transparent
    hwnd=glfw.get_win32_window(w)
    GWL_EXSTYLE=-20;WS_EX_LAYERED=0x80000;LWA_COLORKEY=1
    ctypes.windll.user32.SetWindowLongW(hwnd,GWL_EXSTYLE,
        ctypes.windll.user32.GetWindowLongW(hwnd,GWL_EXSTYLE)|WS_EX_LAYERED)
    # Magenta (R=255,G=0,B=255) = RGB(255,0,255)
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd,0xFF00FF,0,LWA_COLORKEY)
    ctypes.windll.user32.SetWindowPos(hwnd,-1,0,0,0,0,0x0001|0x0002)

    if MODEL.exists():ms,joints,ibm,parent_of,sorted_joints=load(MODEL)
    else:ms,joints,ibm,parent_of,sorted_joints=cube()
    has_bones=ibm is not None
    av=np.vstack([m.v for m in ms]);ct=(av.min(0)+av.max(0))/2;sc=2/(av.max()-av.min()+.01)
    for m in ms:m.v=(m.v-ct)*sc;up(m)

    glEnable(GL_DEPTH_TEST)
    prog=mkprog(VS,FS_TEX)
    proj=persp(35,W/H,.1,100);view=lookat((0,1,4),(0,.3,0),(0,1,0))
    drag=0;ds=(0,0);st="idle";dance_t=0;strength=0.0

    def mb(win,btn,act,mods):
        nonlocal drag,ds,st,dance_t,strength
        if btn==0 and act==1:
            drag=1;ds=glfw.get_cursor_pos(win);st="dancing";dance_t=time.time()
            # Notify main app via UDP
            try:
                s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                s.sendto(b"click",("127.0.0.1",19877))
                s.close()
            except:pass
        elif btn==0:drag=0;st="idle";strength=0

    def mm(win,x,y):
        nonlocal drag,ds
        if drag:
            dx=x-ds[0];dy=y-ds[1]
            if abs(dx)>2 or abs(dy)>2:cx,cy=glfw.get_window_pos(win);glfw.set_window_pos(win,cx+int(dx),cy+int(dy))

    glfw.set_mouse_button_callback(w,mb);glfw.set_cursor_pos_callback(w,mm)

    state_file=ROOT/"pet_state.txt"
    while not glfw.window_should_close(w):
        # Check click file from main app (for external click trigger)
        if (ROOT/"pet_click.txt").exists():
            try:(ROOT/"pet_click.txt").unlink()
            except:pass

        glfw.poll_events();t=time.time()
        glClearColor(*MAGENTA);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)

        # Read state from main app
        try:
            if state_file.exists():
                fs=state_file.read_text().strip()
                if fs=="dancing":st="dancing";dance_t=time.time()
                elif fs in("idle","thinking","responding"):st=fs
        except:pass

        if st=="idle":bob=math.sin(t*2.5)*.012;strength*=.95
        elif st=="dancing":
            e=t-dance_t;bob=abs(math.sin(t*8))*.03;strength=min(1,strength+.05)
            if e>5:st="idle"
        elif st=="thinking":bob=math.sin(t*1.8)*.008;strength*=.95
        elif st=="responding":bob=math.sin(t*3.5)*.022;strength*=.95
        else:bob=0

        # Bone matrices
        bones=np.zeros((64,4,4),'f4')
        for i in range(64):bones[i]=np.identity(4,'f4')
        if has_bones and strength>0.001:
            n=len(joints);lm=np.zeros((n,4,4),'f4')
            for i in range(n):lm[i]=np.identity(4,'f4')
            bpm=120;beat=t*(bpm/60.0)*math.pi
            body_sway=math.sin(beat*0.5)*0.08*strength
            sw_L=math.sin(beat)*0.25*strength+math.sin(beat*2)*0.08*strength
            sw_R=math.sin(beat+math.pi)*0.25*strength+math.sin(beat*2+math.pi)*0.08*strength
            kk_L=math.sin(beat*0.5)*0.12*strength
            kk_R=math.sin(beat*0.5+math.pi)*0.12*strength
            head_nod=math.sin(beat*2)*0.04*strength
            node_to_ji={joints[i]:i for i in range(n)}
            for ni in[1,2,3]:
                if ni in node_to_ji:lm[node_to_ji[ni]]=rot_axis((0,0,1),body_sway)
            for ni in[45,46]:
                if ni in node_to_ji:lm[node_to_ji[ni]]=rot_axis((1,0,0),sw_L)@rot_axis((0,0,1),sw_L*0.5)
            for ni in[49,50]:
                if ni in node_to_ji:lm[node_to_ji[ni]]=rot_axis((1,0,0),sw_R)@rot_axis((0,0,1),sw_R*0.5)
            for ni in[52,53]:
                if ni in node_to_ji:lm[node_to_ji[ni]]=rot_axis((1,0,0),kk_L)
            for ni in[56,57]:
                if ni in node_to_ji:lm[node_to_ji[ni]]=rot_axis((1,0,0),kk_R)
            if 5 in node_to_ji:lm[node_to_ji[5]]=rot_axis((1,0,0),head_nod)
            for j in sorted_joints:
                ni=joints[j]
                if ni in parent_of and parent_of[ni] in node_to_ji:
                    pj=node_to_ji[parent_of[ni]]
                    if pj<j:lm[j]=lm[pj]@lm[j]
            for i in range(n):bones[i]=lm[i]@ibm[i]

        body_turn=0
        if st=="dancing" and strength>0:body_turn=math.sin((t-dance_t)*1.2)*0.6*strength
        model=ry(math.pi+body_turn);model[1,3]=bob
        mvp=proj@view@model
        glUseProgram(prog)
        glUniformMatrix4fv(glGetUniformLocation(prog,"uMVP"),1,GL_TRUE,mvp)
        glUniformMatrix4fv(glGetUniformLocation(prog,"uModel"),1,GL_TRUE,model)
        for i in range(64):
            glUniformMatrix4fv(glGetUniformLocation(prog,f"uBones[{i}]"),1,GL_TRUE,bones[i])
        for m in ms:
            glUniform1i(glGetUniformLocation(prog,"uSkinned"),1 if(m.skinned and has_bones)else 0)
            if m.tid:glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,m.tid)
            glBindVertexArray(m.vao);glDrawElements(GL_TRIANGLES,m.cnt,GL_UNSIGNED_INT,None)
        glfw.swap_buffers(w)
    glfw.terminate()

if __name__=="__main__":main()