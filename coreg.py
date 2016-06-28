import numpy as np
import cv2
import os, inspect, sys, math
from osgeo import gdal
import score

verbose = 0

def ApplyTransform( inFileName, outFileName, tx, ty):
	ds 				= gdal.Open( inFileName )
	geotransform	= ds.GetGeoTransform()
	minX			= geotransform[0]
	maxY  			= geotransform[3]
	pres			= geotransform[1]
	
	#print geotransform
	#print minX, maxY
	
	minX			-= tx*pres
	maxY			+= ty*pres

	#print minX, maxY
	
	ngeot			= (minX, pres, 0.0, maxY, 0.0, -pres )
	driver 			= gdal.GetDriverByName( "GTiff" )
	
	dst_ds 			= driver.CreateCopy( outFileName, ds, 0,	[ 'COMPRESS=DEFLATE' ] )
	dst_ds.SetGeoTransform( ngeot )
	dst_ds 			= None

	print "Transformed to", outFileName
	print ngeot
	
#	
# Compute Root Mean Square Error of results
#	We expect the lines to be parallel (simple translation) aka same slope
#	Compute average slope and then the root mean square error of deviations
#
def RMSE(kp_pairs, status, maxCount=10):
	mse 	= 0
	num 	= 0
	slope	= 0
	p1 		= np.int32([kpp[0].pt for kpp in kp_pairs])
	p2 		= np.int32([kpp[1].pt for kpp in kp_pairs])
	
	slopes 	= []
	mslope	= 0
	for (x1, y1), (x2, y2), inlier in zip(p1, p2, status):
		if inlier:
			if y2 == y1:
				current_slope = 0
			else:
				current_slope 	=  float(x2-x1) / float(y2-y1)
			mslope			+= current_slope
			slopes.append(current_slope)
			
	# mean slope
	mslope	/= len(slopes)
	# mean square error
	mse		= 0
	for s in slopes :
		mse += (s-mslope)**2
		
	nlen	= len(slopes)
	
	# root mean square error
	rmse 	= math.sqrt(mse/nlen)	
	
	print "RMSE", rmse, "-", nlen, "/", len(status)
	
	return rmse, nlen, len(status)

def TxTy( kp_pairs, status, maxCount=10):
	num 	= 0
	tx		= 0
	ty		= 0
	 
	p1 		= np.int32([kpp[0].pt for kpp in kp_pairs])
	p2 		= np.int32([kpp[1].pt for kpp in kp_pairs])
	
	for (x1, y1), (x2, y2), inlier in zip(p1, p2, status):
		if inlier:
			tx		+= (x2-x1)
			ty		+= (y2-y1)
			num		+= 1
	
	tx /= num
	ty /= num
	
	print "tx=", tx
	print "ty=", ty
	
	return tx, ty

def explore_match(img1, img2, kp_pairs, status = None, H = None, maxCount=20):
	h1, w1 = img1.shape[:2]
	h2, w2 = img2.shape[:2]
	#print "explore_match", h1,w1,h2,w2
	vis = np.zeros((max(h1, h2), w1+w2), np.uint8)
	vis[:h1, :w1] = img1
	vis[:h2, w1:w1+w2] = img2
	vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)

	#if H is not None:
	#	corners = np.float32([[0, 0], [w1, 0], [w1, h1], [0, h1]])
	#	corners = np.int32( cv2.perspectiveTransform(corners.reshape(1, -1, 2), H).reshape(-1, 2) + (w1, 0) )
	#	cv2.polylines(vis, [corners], True, (255, 255, 255))

	if status is None:
		status = np.ones(len(kp_pairs), np.bool_)
	
	p1 = np.int32([kpp[0].pt for kpp in kp_pairs])
	p2 = np.int32([kpp[1].pt for kpp in kp_pairs]) + (w1, 0)

	green 		= (0, 255, 0)
	red 		= (0, 0, 255)
	white 		= (255, 255, 255)
	kp_color 	= (51, 103, 236)
	num			= 0
	for (x1, y1), (x2, y2), inlier in zip(p1, p2, status):
		if inlier:
			col = green
			cv2.circle(vis, (x1, y1), 2, col, -1)
			cv2.circle(vis, (x2, y2), 2, col, -1)
			num += 1
			if num == maxCount: break
		
		#else:
		#	col = red
		#	r = 2
		#	thickness = 3
		#	cv2.line(vis, (x1-r, y1-r), (x1+r, y1+r), col, thickness)
		#	cv2.line(vis, (x1-r, y1+r), (x1+r, y1-r), col, thickness)
		#	cv2.line(vis, (x2-r, y2-r), (x2+r, y2+r), col, thickness)
		#	cv2.line(vis, (x2-r, y2+r), (x2+r, y2-r), col, thickness)
	#vis0 = vis.copy()
	num = 0
	for (x1, y1), (x2, y2), inlier in zip(p1, p2, status):
		if inlier:
			cv2.line(vis, (x1, y1), (x2, y2), green)
			num += 1
			if num == maxCount: break
	return vis

def filter_matches(kp1, kp2, matches, ratio = 0.75):
    mkp1, mkp2 = [], []
    for m in matches:
        if len(m) == 2 and m[0].distance < m[1].distance * ratio:
            m = m[0]
            mkp1.append( kp1[m.queryIdx] )
            mkp2.append( kp2[m.trainIdx] )
    p1 = np.float32([kp.pt for kp in mkp1])
    p2 = np.float32([kp.pt for kp in mkp2])
    kp_pairs = zip(mkp1, mkp2)
    return p1, p2, kp_pairs
		
def Compute_RMSE(which, img1, img2, outFile, detector, matcher):
	
	# find the keypoints and descriptors
	kp1, desc1 = detector.detectAndCompute(img1,None)
	kp2, desc2 = detector.detectAndCompute(img2,None)
	print 'img1 - %d features, img2 - %d features' % (len(kp1), len(kp2))

	if len(kp2) == 0:
		return 0, 0, 10000, 0, 0
		
	raw_matches 		= matcher.knnMatch(desc1, trainDescriptors = desc2, k = 2) #2
	p1, p2, kp_pairs 	= filter_matches(kp1, kp2, raw_matches)
	
	if len(p1) >= 4:
		H, status = cv2.findHomography(p1, p2, cv2.RANSAC, 5.0)
		#print '%d / %d  inliers/matched' % (np.sum(status), len(status))
	else:
		H, status = None, None
		print '%d matches found, not enough for homography estimation' % len(p1)
		return 0, 0, 10000, 0, 0
		
	vis 			= explore_match(img1, img2, kp_pairs, status, H)
	rmse,num, nlen 	= RMSE(kp_pairs, status)
	tx, ty 			= TxTy(kp_pairs, status)
	
	#img2	= cv2.drawKeypoints(gray,kp)
	cv2.imwrite(outFile, vis)
	#print "check", outFile
	return tx, ty, rmse, num, nlen


def SURF_RMSE(img1, img2, outFile):
	detector 	= cv2.SURF()
	norm 		= cv2.NORM_L2
	matcher		= cv2.BFMatcher(norm)
	outFile		+= "_SURF.TIF"
	
	return Compute_RMSE('SURF', img1, img2, outFile, detector, matcher)

def SIFT_RMSE(img1, img2, outFile):
	detector	= cv2.SIFT()
	norm 		= cv2.NORM_L2
	matcher		= cv2.BFMatcher(norm)
	outFile		+= "_SIFT.TIF"

	return Compute_RMSE('SIFT', img1, img2, outFile, detector, matcher)

def ORB_RMSE(img1, img2, outFile):
	detector	= cv2.ORB()
	norm 		= cv2.NORM_HAMMING
	matcher		= cv2.BFMatcher(norm)
	outFile		+= "_ORB.TIF"
	
	return Compute_RMSE('ORB', img1, img2, outFile, detector, matcher)

#
# Compute features in an image using the three methods to try to anticipate which method may be best
#
def computeFeatures(fileName):
	img 			= cv2.imread(fileName,0)
	
	surfDetector	= cv2.SURF()
	kp1, desc1 		= surfDetector.detectAndCompute(img,None)
	
	siftDetector	= cv2.SIFT()
	kp2, desc2 		= siftDetector.detectAndCompute(img,None)

	orbDetector		= cv2.ORB(5000)
	kp3, desc3 		= orbDetector.detectAndCompute(img,None)
	print "Detected Features SURF: %d SIFT: %d, ORB: %d" %( len(kp1), len(kp2), len(kp3) )
	
	
	
#def apply( glsChipImage, eo1ChipImage, eo1Image, eo1Scene, _verbose ):
def apply( solution ):
	global verbose
	
	algos			= ['NONE','SURF','SIFT','ORB']
	
	verbose 		= solution['verbose']
	eo1ChipImage 	= solution['eo1Chip']
	glsChipImage 	= solution['refChip']
	eo1Scene 		= solution['eo1Scene']
	eo1Image 		= solution['eo1InputFilename']
	
	base_dir		= os.path.dirname(eo1ChipImage)
	
	print "Co-registering:", glsChipImage, eo1ChipImage
	
	beforeImage	 		= os.path.join(base_dir,"KP_BEFORE.TIF")
	afterImage	 		= os.path.join(base_dir,"KP_AFTER.TIF")
	warpedImage 		= os.path.join(base_dir,"NDVI_"+eo1Scene +"_WARPED.TIF")
	
	img1 				= cv2.imread(glsChipImage,0)
	img2 				= cv2.imread(eo1ChipImage,0)

	tx1, ty1,rmse1, n1, l1 = SURF_RMSE(img1, img2, beforeImage)
	print "*** SURF *** 1 tx: %d ty: %d rmse: %f inliers: %d total: %d" % (tx1, ty1, rmse1, n1, l1)

	tx2, ty2, rmse2, n2, l2 = SIFT_RMSE(img1, img2, beforeImage)
	print "*** SIFT *** 2 tx: %d ty: %d rmse: %f inliers: %d total: %d" % (tx2, ty2, rmse2, n2, l2)
		
	tx3, ty3, rmse3, n3, l3 = ORB_RMSE(img1, img2, beforeImage)
	print "*** ORB *** 3 tx: %d ty: %d rmse: %f inliers: %d total: %d" % (tx3, ty3, rmse3, n3, l3)
	
	results = [
		score.result(1, tx1, ty1, rmse1, n1, l1, 0),
		score.result(2, tx2, ty2, rmse2, n2, l2, 0),
		score.result(3, tx3, ty3, rmse3, n3, l3, 0)
	]
	
	# Pick the best results
	# most features, most inliers and total, least rmse
	best = score.best(results)
	
	if best.rmse < 1:
		print "Selected", best.id, best.tx, best.ty
		solution['algo'] 	= algos[best.id]
		solution['tx']		= best.tx
		solution['ty']		= best.ty
		solution['rmse']	= best.rmse
		solution['status']	= 'SUCCESS'
		ApplyTransform( eo1Image, warpedImage, best.tx, best.ty)
	else:
		print "Failed!!!!"
	
if __name__ == '__main__':
	glsChipImage 		= "/Volumes/proddata/ali_l1g/2016/133/EO1A1400262016133110K2/13022010030.TIF"
	eo1ChipImage		= "/Volumes/proddata/ali_l1g/2016/133/EO1A1400262016133110K2/ndvi_4326.tif"
	
	if not os.path.exists(glsChipImage):
		print "file does not exist", glsChipImage
		sys.exit(-1)
		
	if not os.path.exists(eo1ChipImage):
		print "file does not exist", eo1ChipImage
		sys.exit(-1)
		
	img1 				= cv2.imread(glsChipImage,0)
	img2 				= cv2.imread(eo1ChipImage,0)
	
	
	base_dir	= os.path.dirname(eo1ChipImage)
 	beforeImage	= os.path.join(base_dir,"FULL_KP_BEFORE.TIF")
	
	tx, ty, rmse, n, l = SURF_RMSE(img1, img2, beforeImage)
	tx, ty, rmse, n, l = SIFT_RMSE(img1, img2, beforeImage)
	tx, ty, rmse, n, l = ORB_RMSE(img1, img2, beforeImage)
	 