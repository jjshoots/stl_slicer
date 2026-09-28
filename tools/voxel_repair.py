# Substitute for Blender voxel remesh: 3-axis ray-parity voxelisation (majority vote) at H mm,
# then manifold3d.Manifold.level_set (marching tetrahedra, manifold by construction) at EDGE mm.
import sys, time, numpy as np, trimesh
from manifold3d import Manifold, Mesh as MM, OpType
H=float(sys.argv[1]); EDGE=float(sys.argv[2]); OUT=sys.argv[3]
t0=time.time()
d=np.load("cleaned.npz"); v=d["v"]; f=d["f"].astype(np.int64); lab=np.load("labels.npy")
BOXES=[258,259,260,261,262]   # 12-face frame bars + 2 mm origin cube (already-valid closed boxes)
keep=~np.isin(lab,BOXES); F=f[keep]
used=np.unique(F); lo=v[used].min(0); hi=v[used].max(0)
origin=lo-3*H+np.array([0.0137,0.0291,0.0173])*H   # jitter so rays avoid shared edges/vertices
shape=np.ceil((hi-origin)/H+3).astype(int)
print("voxel grid",shape.tolist(),"=%.0fM"%(np.prod(shape)/1e6),"h",H,flush=True)
tri=v[F]
def parity(axis):
    a,b=[x for x in range(3) if x!=axis]; c=axis
    na,nb,nc=shape[a],shape[b],shape[c]
    acc=np.zeros(na*nb*nc,np.uint8)
    for s in range(0,len(tri),400000):
        T=tri[s:s+400000]; A=T[:,:,a];B=T[:,:,b];C=T[:,:,c]
        imin=np.ceil((A.min(1)-origin[a])/H-0.5).astype(np.int64); imax=np.floor((A.max(1)-origin[a])/H-0.5).astype(np.int64)
        jmin=np.ceil((B.min(1)-origin[b])/H-0.5).astype(np.int64); jmax=np.floor((B.max(1)-origin[b])/H-0.5).astype(np.int64)
        ni=(imax-imin+1).clip(0); nj=(jmax-jmin+1).clip(0); cnt=ni*nj
        idx=np.repeat(np.arange(len(T)),cnt); k=np.arange(cnt.sum())-np.repeat(np.cumsum(cnt)-cnt,cnt)
        i=imin[idx]+k//np.maximum(nj[idx],1); j=jmin[idx]+k%np.maximum(nj[idx],1)
        pa=origin[a]+(i+0.5)*H; pb=origin[b]+(j+0.5)*H
        x0,x1,x2=A[idx,0],A[idx,1],A[idx,2]; y0,y1,y2=B[idx,0],B[idx,1],B[idx,2]
        den=(y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
        with np.errstate(divide="ignore",invalid="ignore"):
            l0=((y1-y2)*(pa-x2)+(x2-x1)*(pb-y2))/den; l1=((y2-y0)*(pa-x2)+(x0-x2)*(pb-y2))/den
        l2=1-l0-l1; ok=(den!=0)&(l0>=0)&(l1>=0)&(l2>=0)
        depth=l0*C[idx,0]+l1*C[idx,1]+l2*C[idx,2]
        kk=np.ceil((depth-origin[c])/H-0.5).astype(np.int64)
        ok&=(kk>=0)&(kk<nc)
        flat=(i[ok]*nb+j[ok])*nc+kk[ok]
        u,n=np.unique(flat,return_counts=True); acc[u]^=(n&1).astype(np.uint8)
    acc=acc.reshape(na,nb,nc); np.bitwise_xor.accumulate(acc,axis=2,out=acc)
    # move back to x,y,z order
    perm=[0,0,0]; perm[a]=0; perm[b]=1; perm[c]=2
    return np.transpose(acc,perm).astype(bool)
votes=np.zeros(shape,np.uint8)
per=[]
for ax in (2,0,1):
    t=time.time(); p=parity(ax); votes+=p; per.append(p.sum()); print(" axis",ax,"inside voxels",p.sum(),"%.1fs"%(time.time()-t),flush=True); del p
occ=votes>=2
agree=(votes==0)|(votes==3); print("majority inside voxels",occ.sum(),"volume %.0f mm3"%(occ.sum()*H**3),"axis disagreement voxels",(~agree).sum(),flush=True)
del votes, agree
# 3x3x3 box blur -> smooth field in [0,1]
g=occ.astype(np.float32); del occ
del tri
for ax in range(3):
    o=g.copy(); sl=lambda s,e:tuple(slice(s,e) if q==ax else slice(None) for q in range(3))
    o[sl(1,None)]+=g[sl(None,-1)]; o[sl(None,-1)]+=g[sl(1,None)]; o/=3; g=o; del o
g-=0.5
nx,ny,nz=shape; flat=g.ravel(); mv=memoryview(flat)
ox,oy,oz=(origin+0.5*H).tolist(); inv=1.0/H
calls=[0]
NYZ=ny*nz
def sdf(x,y,z):
    fx=(x-ox)*inv; fy=(y-oy)*inv; fz=(z-oz)*inv
    i=int(fx); j=int(fy); k=int(fz)
    if fx<0 or fy<0 or fz<0 or i>=nx-1 or j>=ny-1 or k>=nz-1: return -0.5
    tx=fx-i; ty=fy-j; tz=fz-k; b0=i*NYZ+j*nz+k; b1=b0+NYZ
    c00=mv[b0]*(1-tz)+mv[b0+1]*tz; c01=mv[b0+nz]*(1-tz)+mv[b0+nz+1]*tz
    c10=mv[b1]*(1-tz)+mv[b1+1]*tz; c11=mv[b1+nz]*(1-tz)+mv[b1+nz+1]*tz
    return (c00*(1-ty)+c01*ty)*(1-tx)+(c10*(1-ty)+c11*ty)*tx
b=[*(origin+H).tolist(),*(origin+(shape-1)*H).tolist()]
t=time.time(); M=Manifold.level_set(sdf,b,EDGE); print("level_set %.1fs status %s tris %d vol %.0f"%(time.time()-t,M.status().name,M.num_tri(),M.volume()),flush=True)
mo=M.to_mesh(); tm=trimesh.Trimesh(np.asarray(mo.vert_properties)[:,:3],np.asarray(mo.tri_verts),process=False)
print("bounds",tm.bounds.round(2).tolist()); tm.export(OUT)
# variant with the original frame boxes + origin cube unioned back in
parts=[M]
for bid in BOXES:
    Fb=f[lab==bid]; ub,ib=np.unique(Fb.ravel(),return_inverse=True)
    parts.append(Manifold(MM(vert_properties=np.ascontiguousarray(v[ub],np.float32),tri_verts=np.ascontiguousarray(ib.reshape(-1,3),np.uint32))))
U=Manifold.batch_boolean(parts,OpType.Add); mo=U.to_mesh()
trimesh.Trimesh(np.asarray(mo.vert_properties)[:,:3],np.asarray(mo.tri_verts),process=False).export(OUT.replace(".stl","_with_frame.stl"))
print("with frame: tris %d vol %.0f"%(U.num_tri(),U.volume()),"total %.1fs"%(time.time()-t0))
