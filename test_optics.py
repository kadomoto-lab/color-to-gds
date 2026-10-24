import numpy as np
from optics import solve,eps,color,WL,planar_reflectance
def test_white_black():
    c=color(np.ones_like(WL)); assert abs(c['XYZ'][1]-1)<1e-10
    assert np.max(np.abs(np.array(c['rgb'])-1))<.002
    assert max(color(np.zeros_like(WL))['rgb'])==0
def test_planar_against_independent_fresnel_recursion():
    for w in [403,551,703]:
        a=solve(w,.4,.2,'flat_m1',modes=11)
        assert np.max(abs(a[:,0]-planar_reflectance(w)))<1e-6
def test_passive_energy_and_orders():
    for w in [405,555,705]:
        a=solve(w,.64,.28,modes=31)
        assert np.isfinite(a).all()
        assert np.min(a)>-1e-6
        assert np.max(a[:,1]+a[:,2])<1+1e-6
        assert np.all(a[:,0]<=a[:,1]+1e-6)
def test_uniform_limit():
    # Fully filled pattern must reduce to a uniform Al film on same underlying layers.
    a=solve(553,.4,.4,modes=11)
    b=solve(553,.4,.4,modes=21)
    assert np.max(abs(a-b))<1e-6
def test_li_does_not_change_te():
    a=solve(557,.44,.2,modes=21,li=True)
    b=solve(557,.44,.2,modes=21,li=False)
    assert np.max(abs(a[0]-b[0]))<1e-7


def test_full_grating_against_uniform_film_reference():
    from optics import layers
    for w in [413,567,711]:
        st=layers('m2_m1_mirror')
        ns=[1+0j if m=='air' else np.sqrt(eps('Al' if m=='pattern' else m,w)+0j) for m,d in st]
        rr=0j
        for j in range(len(st)-2,-1,-1):
            fres=(ns[j]-ns[j+1])/(ns[j]+ns[j+1])
            phase=np.exp(4j*np.pi*ns[j+1]*st[j+1][1]/(w/1000))
            rr=(fres+rr*phase)/(1+fres*rr*phase)
        a=solve(w,.4,.4,modes=11)
        assert np.max(abs(a[:,0]-abs(rr)**2))<1e-6
