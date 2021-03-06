from boxm2_scene_adaptor import *; 
from bbas_adaptor import *;
from vil_adaptor import *;
from vpgl_adaptor import *;
import random, os, sys, math, scene_registry;  
import numpy as np;

###################################################
# Render helper functions -
# - pointsFromFile - parses point file (x,y,z)s
# - render_save - takes camera and saves image/camera in separate directories
#
#
###################################################

def pointsFromFile(fname):
  """ Point file format:
      <num points>
      <x>  <y>  <z>  
      <x>  <y>  <z>
  """
  f = open(fname, 'r')
  numPts = int(f.readline())
  print numPts
  pts = []
  for line in f:
    pt = [float(x) for x in line.strip().split()]
    pts.append(pt)
  return pts

def interpolatePoints(pts, numBetween):
  """ Create linearly interpolated points between each 
      point in input array 
  """
  if numBetween <= 0:
    return pts
  #create new vector w/ original points distributed evenly
  numPts = len(pts) + (len(pts)-1)*numBetween
  densePts = np.zeros((numPts,3))
  densePts[0::numBetween+1] = pts
  
  #create interpolated points
  for idx in range(0, numPts-1, numBetween+1):
    pt0 = densePts[idx]
    pt1 = densePts[idx+numBetween+1]
    dxyz = (pt1 - pt0)/float(numBetween+1)
    for ii in range(1,numBetween+1):
      densePts[idx+ii] = pt0 + dxyz*ii
  return densePts

def normalize(a):
  """Slow normalization function"""
  if a.size == 3:
    mag = np.sqrt(np.sum(a*a))
    return a / mag
  mag = np.sqrt(np.sum(a*a,1))
  mag = np.tile(mag, (3,1)).T
  return a/mag

def pathNormals(pts, smooth=1):
  """XY normal to each point"""
  points = np.array(pts)
  normDirs = np.zeros(points.shape)
  for idx in range(1, len(points)-1):
    pdir = normalize(points[idx+1] - points[idx-1])
    updir = np.array([0., 0., 1.])
    ndir = normalize(np.cross(pdir, updir))
    normDirs[idx] = ndir
  normDirs[0] = normDirs[1]
  normDirs[-1] = normDirs[-2]
 
  #smooth look dirs, finally calculate look points
  for idx in range(smooth, len(normDirs)-smooth):
    normDirs[idx] = normalize(np.mean(normDirs[idx-smooth:idx+1+smooth],0))
  return normDirs

def pathLookPts(points, incline=45., forwardAngle=45, smooth=20):
  """ Computes the normal to each point (looking 
      45 degrees off nadir)
  """
  points = np.array(points)
  lookPts = np.zeros(points.shape)

  # create jagged normdirs (normal from path direction)
  normDirs = np.zeros(points.shape)
  tanDirs = np.zeros(points.shape)
  curvature = np.zeros(points.shape)
  xyCurve = np.zeros((points.shape[0],))
  for idx in range(1, len(points)-1):
    pdir = normalize(points[idx+1]-points[idx-1])
    updir = np.array([0., 0., 1.])
    ndir = normalize(np.cross(pdir, updir))
    normDirs[idx] = ndir
    tanDirs[idx] = pdir    
    curvature[idx] = (points[idx+1] - 2*points[idx] + points[idx-1])/2.
    xyCurve[idx] = curvature[idx][0]*curvature[idx][0] + curvature[idx][1]*curvature[idx][1]  

  #hack set off by ones
  tanDirs[0] = tanDirs[1]
  tanDirs[-1] = tanDirs[-2]
  curvature[0] = curvature[1]
  curvature[-1] = curvature[-2]
  normDirs[0] = normDirs[1]
  normDirs[-1] = normDirs[-2]

  #calculate lookdirs
  lookDirs = np.zeros(points.shape)
  for idx in range(len(points)):
    #lookpoint on the ground
    lookDir = tanDirs[idx] + (1 + 100000*xyCurve[idx]) * normDirs[idx] 
    lookDirs[idx] = normalize(lookDir)    
    lookDirs[idx] = normDirs[idx]

  #smooth look dirs, finally calculate look points
  for idx in range(smooth, len(normDirs)-smooth):
    lookDirs[idx] = normalize(np.mean(lookDirs[idx-smooth:idx+1+smooth],0))

  #calculate look dirs
  for idx in range(len(points)):
    groundDist = points[idx][2] * math.tan(math.radians(incline))
    lookPt = np.array([points[idx][0], points[idx][1], 0.0]) + groundDist * lookDirs[idx]
    lookPts[idx] = lookPt
  return lookPts


def render_save(scene, cam, globalIdx, trajDir, camDir, NI=1280, NJ=720):
  """method for rendering/saving/incrementing globalIdx"""
  #render image/convert to bimg
  expimg = scene.render(cam, NI, NJ);
  bimg   = convert_image(expimg); 
  exp_fname = trajDir + "/exp_%(#)06d.png"%{"#":globalIdx};
  save_image(bimg, exp_fname); 

  #save cam
  cam_name = camDir + "/cam_%(#)06d.txt"%{"#":globalIdx}
  save_perspective_camera(cam, cam_name)
  remove_from_db([cam, expimg, bimg])


def renderSpiral(lookPt, camCenter, dCamCenter, numImages):
  """ render a spiral around a look point returns cam center it ends up on
      lookPt (center of spiral)
      camCenter (az,inc,rad) w.r.t. lookPt
  """
  global globalIdx
  for idx in range(numImages):
    print "Rendering # ", idx, "of", numImages
    #create cam, and render
    currAz,currInc,currR = camCenter
    center = get_camera_center(currAz, currInc, currR, lookPt)
    cam = create_perspective_camera( (fLength,fLength), ppoint, center, lookPt )
    render_save(cam)
    #increment az, incline and radius
    camCenter = numpy.add(camCenter, dCamCenter)
  return camCenter

def drift(look0, look1, camCenter, numImages):
  """ drift view to a new look point, smoothly """
  #calc input XYZ center about look0
  currAz, currInc, currR = camCenter
  center = get_camera_center(currAz, currInc, currR, look0)
  #calc drift val, and store lookPt
  lookPt = look0
  drift = numpy.subtract(look1,look0)/numImages
  for idx in range(numImages):
    cam = create_perspective_camera( (fLength,fLength), ppoint, center, lookPt )
    render_save(cam)
    lookPt = numpy.add(lookPt, drift)
    center = numpy.add(center, drift)
  return center

def lookSmooth(point0, point1, camCenter, numImgs, dCamCenter=(0,0,0)): 
  """ take a camera looking at point0, with 
      center = (az, inc, rad), and look at poitn1
  """
  global globalIdx
  print "gazing from ", point0, "to", point1
  az, inc, rad = camCenter; 
  lDiff = numpy.subtract(point1, point0)
  dLook = numpy.divide(lDiff, numImgs)
  lpoint = point0
  for idx in range(numImgs):
    #create cam, and render
    center = get_camera_center(az, inc, rad, modCenter)
    cam = create_perspective_camera( (fLength,fLength), ppoint, center, lpoint )
    expimg = scene.render(cam, NI, NJ);
    bimg   = convert_image(expimg); 
    exp_fname = trajDir + "/exp_%(#)03d.png"%{"#":globalIdx};
    globalIdx+=1
    save_image(bimg, exp_fname); 
    remove_from_db([cam, expimg, bimg])

    #increment az, incline and radius
    lpoint = numpy.add(lpoint, dLook)


