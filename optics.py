"""1D lamellar RCWA; um, exp(-i omega t), passive n+ik.
Analytic rectangular Fourier coefficients; Li inverse rule for normal E.
grcwa supplies eigensystems and stable multilayer scattering matrices.
"""
from pathlib import Path
from functools import lru_cache
import numpy as np
import yaml, grcwa, colour
from grcwa.rcwa import MakeKPMatrix, SolveLayerEigensystem
ROOT=Path(__file__).resolve().parent
WL=np.arange(380.,781.,5.)
D65=colour.SDS_ILLUMINANTS['D65'].copy().align(colour.SpectralShape(380,780,5)).values
CMF=colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer'].copy().align(colour.SpectralShape(380,780,5)).values
WHITE=colour.CCS_ILLUMINANTS['CIE 1931 2 Degree Standard Observer']['D65']

@lru_cache(None)
def table(material):
    d=yaml.safe_load((ROOT/'data'/f'{material}.yml').read_text())
    return np.array([list(map(float,s.split())) for s in d['DATA'][0]['data'].splitlines() if s.strip()])
def eps(material,wl):
    if material=='oxide':
        l=wl/1000
        return 1+sum(b*l*l/(l*l-c*c) for b,c in [(0.6961663,0.0684043),(0.4079426,0.1162414),(0.8974794,9.896161)])
    if material=='nitride': return 2.0**2 # optical assumption, NOT sqrt(PDK static K)
    if material=='polyimide': return 1.65**2 # optical assumption; loss neglected
    t=table(material)
    l=wl/1000
    if l<t[0,0] or l>t[-1,0]: raise ValueError('No extrapolation of optical constants')
    n=np.interp(l,t[:,0],t[:,1]); k=np.interp(l,t[:,0],t[:,2])
    return (n+1j*k)**2

def color(spectrum, wavelengths=WL):
    # Relative XYZ; perfect white has Y=1. No per-spectrum renormalization.
    wl=np.asarray(wavelengths)
    if np.array_equal(wl,WL):
        d65,cmf=D65,CMF
    else:
        step=float(wl[1]-wl[0])
        assert np.allclose(np.diff(wl),step)
        shape=colour.SpectralShape(float(wl[0]),float(wl[-1]),step)
        d65=colour.SDS_ILLUMINANTS['D65'].copy().align(shape).values
        cmf=colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer'].copy().align(shape).values
    xyz=np.trapezoid(np.asarray(spectrum)[...,None]*d65[:,None]*cmf,wl,axis=-2)/np.trapezoid(d65*cmf[:,1],wl)
    rgb=colour.XYZ_to_sRGB(xyz)
    return {'XYZ':xyz.tolist(),'Lab':colour.XYZ_to_Lab(xyz,WHITE).tolist(),
            'xy':colour.XYZ_to_xy(xyz).tolist(),'rgb':np.clip(rgb,0,1).tolist(),
            'out_of_srgb':bool(np.any((rgb<0)|(rgb>1)))}

def layers(family,cap=4.355,nitride=.3777,pi=0.,metal=.36,gap=.27):
    # Top to bottom; empty M3-M5 levels treated as silica, bottom M1=1.3761 um.
    result=[('air',0.)]
    if pi: result.append(('polyimide',pi))
    if nitride: result.append(('nitride',nitride))
    result.append(('oxide',cap))
    if family=='m1_grating':
        result += [('oxide',metal+gap),('pattern',metal),('oxide',1.3761)]
    elif family=='m2_grating':
        result += [('pattern',metal),('oxide',gap+metal+1.3761)]
    elif family=='m2_m1_mirror':
        result += [('pattern',metal),('oxide',gap),('Al',metal),('oxide',1.3761)]
    elif family=='flat_m1':
        result += [('oxide',metal+gap),('Al',metal),('oxide',1.3761)]
    else: raise ValueError(family)
    return result+[('Si',0.)]

def solve(wl,pitch,width,family='m2_m1_mirror',modes=31,theta=0.,cap=4.355,nitride=.3777,pi=0.,metal=.36,gap=.27,li=True):
    if modes%2!=1: raise ValueError('modes must be odd')
    stack=layers(family,cap,nitride,pi,metal,gap)
    # Very short fictitious y period excludes all nonzero Gy orders.
    # Tiny imaginary frequency regularizes exact grazing Rayleigh orders.
    o=grcwa.obj(modes+1,[pitch,0],[0,pitch/(modes*4)],(1+1e-10j)/(wl/1000),np.deg2rad(theta),0,verbose=0)
    for mat,d in stack:
        if mat=='pattern': o.Add_LayerGrid(d,1,1)
        else: o.Add_LayerUniform(d,1. if mat=='air' else eps(mat,wl))
    o.Init_Setup()
    assert o.nG==modes and np.all(o.G[:,1]==0)
    if any(mat=='pattern' for mat,_ in stack):
        m=o.G[:,0]; dm=m[:,None]-m[None,:]; fill=width/pitch
        shape=fill*np.sinc(dm*fill)*np.exp(-1j*np.pi*dm)
        eye=np.eye(o.nG); ea=eps('Al',wl); ed=eps('oxide',wl)
        conv=ed*eye+(ea-ed)*shape
        invconv=(1/ed)*eye+(1/ea-1/ed)*shape
        epinv=np.linalg.inv(conv)
        ex=np.linalg.inv(invconv) if li else conv
        z=np.zeros_like(conv); ep2=np.block([[conv,z],[z,ex]]) # grcwa uses rotated (-Ey, Ex) order
        for i,(mat,_) in enumerate(stack):
            if mat!='pattern': continue
            j=o.id_list[i][2]
            o.Patterned_epinv_list[j]=epinv; o.Patterned_ep2_list[j]=ep2
            kp=MakeKPMatrix(o.omega,1,epinv,o.kx,o.ky)
            q,phi=SolveLayerEigensystem(o.omega,o.kx,o.ky,kp,ep2)
            o.kp_list[i]=kp; o.q_list[i]=q; o.phi_list[i]=phi
    values=[]
    for pol in ['s','p']:
        o.MakeExcitationPlanewave(p_amp=int(pol=='p'),p_phase=0,s_amp=int(pol=='s'),s_phase=0)
        r,t=o.RT_Solve(normalize=1,byorder=1)
        i0=np.flatnonzero(np.all(o.G==0,axis=1))[0]
        values.append([float(np.real(r[i0])),float(np.real(np.sum(r))),float(np.real(np.sum(t)))])
    return np.array(values) # pol x [R0, Rtotal, T into silicon]

def spectrum(pitch,width,family='m2_m1_mirror',wavelengths=WL,**kw):
    return np.array([solve(w,pitch,width,family,**kw) for w in wavelengths])

def planar_reflectance(wl,family='flat_m1',**kw):
    st=layers(family,**kw)
    ns=np.array([1 if m=='air' else np.sqrt(eps(m,wl)+0j) for m,d in st])
    rr=0j
    for j in range(len(st)-2,-1,-1):
        fres=(ns[j]-ns[j+1])/(ns[j]+ns[j+1])
        phase=np.exp(4j*np.pi*ns[j+1]*st[j+1][1]/(wl/1000))
        rr=(fres+rr*phase)/(1+fres*rr*phase)
    return abs(rr)**2


