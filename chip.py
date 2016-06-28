import os, inspect, sys, math, time, glob, io

from quadkey import QuadKey, TileSystem

import quadkey
import config, entropy, coreg
import numpy, scipy
import json, geojson
import cv2

from osgeo import gdal

verbose = 0

def execute( cmd ):
	if verbose:
		print cmd
	os.system(cmd)

def linear_stretch( data, min_percentile=2.0, max_percentile=98.0):

	# In our case, zeros are special.. keep track of them
	# This is a hard one.  We should not have any zeroes in the GLS chip not the original image but we do...
	# zero_mask 	= (data==0)
	
	#pmin, pmax 	= numpy.percentile(data[numpy.nonzero(data)], (min_percentile, max_percentile))
	pmin, pmax 	= numpy.percentile(data, (min_percentile, max_percentile))
	if verbose:
		print "Linear Stretch", pmin, pmax, numpy.count_nonzero(data), data.size
		
	data[data>pmax]=pmax
	data[data<pmin]=pmin
		
	bdata = scipy.misc.bytescale(data, low=1)
	#bdata[zero_mask]=0
	#if verbose:
	#	print "Linear Stretch", numpy.count_nonzero(bdata)
	
	return bdata

def SaveImage(fileName, ds, data):

	if verbose:
		print "Saving to", fileName
	
	# Save it as Byte, compressed
	driver 		= gdal.GetDriverByName( "GTiff" )
	ods			= driver.Create( fileName, ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte,	[ 'COMPRESS=DEFLATE' ] )
	oband 		= ods.GetRasterBand(1)
	
	oband.WriteArray(data, 0, 0)
	ods.SetGeoTransform( ds.GetGeoTransform() )
	ods.SetProjection( ds.GetProjection() )
	
	ods 				= None
		
def subset(minX, minY, maxX, maxY, pixSizeX, pixSizeY, infileName, outFileName):
	# Create gdalwarp command
	ofStr 				= ' -q -of GTiff'
	bbStr 				= ' -te %s %s %s %s '%(minX, minY, maxX, maxY) 
	resStr 				= ' -tr %s %s '%(pixSizeX, pixSizeY)
	#projectionStr 		= ''' -t_srs '%s' ''' %(projection)
	overwriteStr 		= ' -overwrite ' # Overwrite output if it exists
	additionalOptions 	= ' -co COMPRESS=DEFLATE ' # Additional options
	warpOptions 		= ofStr + bbStr + resStr + overwriteStr + additionalOptions

	#if not os.path.exists(outFileName):
	if 1:
		warpCMD = 'gdalwarp ' + warpOptions + infileName + ' ' + outFileName
		if verbose:
			print "subset to:", outFileName
		execute(warpCMD)
	#else:
	#	print "did not make subset", outFileName


# Cut a chip from a scene
def MakeChip(minX, minY, maxX, maxY, pres, orgFileName, glsChipSubsetImage, subsetImage):

	# Create the tile from scene
	subset(minX, minY, maxX, maxY, pres, pres, orgFileName, glsChipSubsetImage)

	ds 				= gdal.Open( glsChipSubsetImage )
	geotransform	= ds.GetGeoTransform()
	
	band 			= ds.GetRasterBand(1)
	data 			= band.ReadAsArray(0, 0, ds.RasterXSize, ds.RasterYSize )

	dtype			= band.DataType
	#print '**Band Type=',gdal.GetDataTypeName(band.DataType), dtype
	
	# Apply Median Filter (required for SOBEL)
	#data 			= scipy.signal.medfilt2d(data.astype(numpy.float32), kernel_size=3)
 
	# Apply Additional Filter
	#data 			= ApplySobelFilter(subsetImage, data)
	# ApplyCannyFilter(chipImage, data)
	
	# Linear Stretch
	data			= linear_stretch(data)
	
	#data[data>0.2]	= 255
	#data[data<=0.2]= 0

	e				= entropy.Shannon(data)
	
	#print "** Entropy", e	#, ds.RasterXSize, ds.RasterYSize
		
	SaveImage(subsetImage, ds, scipy.misc.bytescale(data))

	kp1		 		= coreg.computeFeatures(subsetImage)

	minX			= geotransform[0]
	maxY  			= geotransform[3]
			
	#lower right corner
	maxX			= minX + geotransform[1]* ds.RasterXSize
	minY			= maxY - geotransform[1]* ds.RasterYSize
	samples			= ds.RasterXSize
	lines			= ds.RasterYSize
	
	ds = None
	
	return minX, maxX, minY, maxY, e, samples, lines
	
#
# Return minX,maxX, minY, maxY, samples, lines of a quadkey for that L8 scene
#
#	and let's make square tiles to optimize the co-registration while at it
#
def GetMinMax(ds, bbox):
	geotransform	= ds.GetGeoTransform()
		
	presX			= geotransform[1]
	presY			= geotransform[5]
	
	minX			= bbox['w']
	maxX			= bbox['e']
	minY			= bbox['s']
	maxY			= bbox['n']
	
	# Check how many pixels this would be
	npxX			= int(math.ceil((maxX-minX)/geotransform[1]))
	npxY			= int(math.ceil((maxY-minY)/geotransform[1]))
	
	npx 			= max(npxX, npxY)
		
	samples = lines = npx
			
	maxX			= minX + geotransform[1]* npx
	minY			= maxY - geotransform[1]* npx
	
	samples			= npx
	lines			= npx

	return minX, maxX, minY, maxY, samples, lines
	
def TileBounds(qk):
	[(tx,ty),zoom] 	=  qk.to_tile()
	
	minpixels 		= TileSystem.tile_to_pixel([tx,ty])
	maxlat, minlon 	= TileSystem.pixel_to_geo(minpixels, zoom)
	
	maxpixels 		= TileSystem.tile_to_pixel([tx+1,ty+1])
	minlat, maxlon 	= TileSystem.pixel_to_geo(maxpixels, zoom)
	
	bbox = {
		's': minlat,
		'w': minlon,
		'n': maxlat,
		'e': maxlon
	}
	return bbox

def Feature(q, minX,maxX, minY, maxY):
	
	properties = {
		'name': 		q
	}
	
	feature = { 
		"type": "Feature", 
		"geometry": { 
			"type": "Polygon", 
			"coordinates": [[
				[round(minX,5),round(minY,5)],
				[round(minX,5),round(maxY,5)],
				[round(maxX,5), round(maxY,5)],
				[round(maxX,5), round(minY,5)],
				[round(minX,5), round(minY,5)]
			]]
		}, 
		"properties": properties
	}
	return feature

def makeGeoJSON(features, geojson_filename):
	# Save geojson file
	geojson		= {
		"type": "FeatureCollection", 
		"features": features
	}

	with io.open(geojson_filename, 'w', encoding='utf-8') as f:
		f.write(unicode(json.dumps(geojson, ensure_ascii=False)))
	
def makeKML(features, kml_filename):
	# Save as KML
	kml = "<?xml version='1.0' encoding='UTF-8'?>\n" 
	kml += "<kml xmlns='http://earth.google.com/kml/2.0'> <Document>"
	kml += "<Style id='PolyStyle'><LabelStyle><color>ff0000cc</color></LabelStyle><LineStyle><width>1.5</width><color>ff0000ff</color></LineStyle></Style>"
	
	for f in features:
		coordinates = f['geometry']['coordinates'][0]

		kml += "<Placemark><name>"+f['properties']['name']+"</name>\n"
		kml += "<styleUrl>#PolyStyle</styleUrl>\n"
	
		kml += "<MultiGeometry><Point><coordinates>"
		# now we need the center of that polygon
		lngs = []
		lats = []
		for inner in coordinates:
			lngs.append(inner[0])
			lats.append(inner[1])
	
		lng = (min(lngs)+ max(lngs))/2
		lat = (min(lats)+ max(lats))/2
	 	kml += str(lng)+","+str(lat)+",0"
		kml += "</coordinates></Point>"
	
		kml += "<Polygon>\n"
		kml += "<outerBoundaryIs><LinearRing>\n"
		kml += "<coordinates>\n"
		for inner in coordinates:
			for i in inner:
				kml += str(i)
				kml += ","
			kml += "0\n"
		kml += "</coordinates></LinearRing></outerBoundaryIs></Polygon></MultiGeometry>\n"
	
		#kml += "<Style><PolyStyle><color>#a00000ff</color><outline>1</outline><fill>0</fill></PolyStyle></Style>"
		kml += "</Placemark>\n"

	kml += "</Document></kml>"
	with io.open(kml_filename, 'w', encoding='utf-8') as f:
		f.write(unicode(kml))

# http://geospatialpython.com/2011/08/point-in-polygon-2-on-line.html
# Improved point in polygon test which includes edge
# and vertex points

def point_in_poly(x,y,poly):

   # check if point is a vertex
   if (x,y) in poly: return "IN"

   # check if point is on a boundary
   for i in range(len(poly)):
      p1 = None
      p2 = None
      if i==0:
         p1 = poly[0]
         p2 = poly[1]
      else:
         p1 = poly[i-1]
         p2 = poly[i]
      if p1[1] == p2[1] and p1[1] == y and x > min(p1[0], p2[0]) and x < max(p1[0], p2[0]):
         return "IN"
      
   n = len(poly)
   inside = False

   p1x,p1y = poly[0]
   for i in range(n+1):
      p2x,p2y = poly[i % n]
      if y > min(p1y,p2y):
         if y <= max(p1y,p2y):
            if x <= max(p1x,p2x):
               if p1y != p2y:
                  xints = (y-p1y)*(p2x-p1x)/(p2y-p1y)+p1x
               if p1x == p2x or x <= xints:
                  inside = not inside
      p1x,p1y = p2x,p2y

   if inside: return 1
   else: return 0
   	
#
# Find the quadtiles in the neighborhood of the target at that zoomlevel
#
def GetQuadTiles(centerLat,centerLon, zoomLevel):
	centerHash			= quadkey.from_geo([centerLat,centerLon], zoomLevel)
	qkeys 				= []
	qkeys.append(centerHash.key)
	
	for q in centerHash.nearby():
		qkeys.append(q)
	
	return qkeys
	
def reproject( epsg, in_file, out_file):
	if verbose:
		print "reproject ", in_file, " to:", out_file

	# remove out_file if it already exists
	if os.path.isfile(out_file):
		os.remove(out_file)
		
	cmd = "gdalwarp -of GTiff -co COMPRESS=DEFLATE -t_srs "+ epsg +" " + in_file + " " + out_file
	execute(cmd)

#
# Check quadtile in footsteps
#
def CheckWithin(qk, minX, maxX, minY, maxY, footstepPolygon):
	pt_in = point_in_poly( minX,minY,footstepPolygon)
	if pt_in == 0:
		print "not in footsteps", qk
		return 0
		
	pt_in = point_in_poly( minX,maxY,footstepPolygon)
	if pt_in == 0:
		print "not in footsteps", qk
		return 0

	pt_in = point_in_poly( maxX,maxY,footstepPolygon)
	if pt_in == 0:
		print "not in footsteps", qk
		return 0

	pt_in = point_in_poly( maxX,minY,footstepPolygon)
	if pt_in == 0:
		print "not in footsteps", qk
		return 0

	return 1
#
# Return footsteps polygon
#
def LoadPolygon(eo1FileName):
	base_dir			= os.path.dirname(eo1FileName)
	footstepsFileName 	= os.path.join(base_dir, "geojson", "footsteps.tif.json")
	with open(footstepsFileName) as json_data:
		jsond = geojson.load(json_data)
	json_data.close()
	
	feature = jsond['features'][0]
	coords	= feature['geometry']['coordinates']
	poly	= coords[0]
	return poly
	
# Make sure that all landsat-8 tiles are in same projection
def reprojectEntities( entities, solution ):
	for entityID in entities:
		year			= entityID[9:13]
		doy				= entityID[13:16]

		org_ext 		= solution['reference_ext']
		ext 			= org_ext.replace(".TIF", "_4326.TIF")
		
		
		l8_fileName		= os.path.join(config.DATA_DIR, config.LANDSAT8_DIR, year, doy, entityID, entityID+org_ext)
		l8_4326			= os.path.join(config.DATA_DIR, config.LANDSAT8_DIR, year, doy, entityID, entityID+ext)
	
		if not os.path.exists(l8_4326):
			if not os.path.exists(l8_fileName):
				print "L8 file does not exist to reproject", l8_fileName
				sys.exit(-1)
			
			reproject( "EPSG:4326", l8_fileName, l8_4326)

def mosaicEntities(eo1Scene, entities, solution):
	year			= eo1Scene[10:14]
	doy				= eo1Scene[14:17]
	base_dir		= os.path.join(config.ALI_DIR, year, doy, eo1Scene)
	mosaicFile		= os.path.join(base_dir, "L8_MOSAIC.VRT")
	
	print "Mosaic'ing", entities
	
	cmd = "gdalbuildvrt -srcnodata 0 %s " % mosaicFile

	org_ext 		= solution['reference_ext']
	ext 			= org_ext.replace(".TIF", "_4326.TIF")
		
	for entityID in entities:
		year			= entityID[9:13]
		doy				= entityID[13:16]
		l8_4326			= os.path.join(config.DATA_DIR, config.LANDSAT8_DIR, year, doy, entityID, entityID+ext)
		cmd += l8_4326 + " "
	
	execute( cmd )
	
	return mosaicFile
#
# Find best co-registration chip for that EO-1 scene
#
#def FindBest(eo1Scene, entities, eo1FileName, centerLat, centerLon, zoomLevel, _verbose):
def FindBest(solution):
	global verbose
	
	verbose			= solution['verbose']
	eo1FileName		= solution['eo1InputFilename']
	eo1Scene		= solution['eo1Scene']
	entities		= solution['entities']
	
	eo1_ds 			= gdal.Open( eo1FileName )
	eo1_proj		= eo1_ds.GetProjection()
	
	geotransform	= eo1_ds.GetGeoTransform()
	presX			= geotransform[1]
	presY			= geotransform[5]
	
	pres 			= presX
	assert presX 	== -presY
	
	# Get the potential quadtiles	
	qkeys 			= GetQuadTiles( solution['centerLat'],  solution['centerLon'], solution['zoomLevel'])
			
	reprojectEntities( entities, solution)
	
	l8_mosaic 		= mosaicEntities(eo1Scene, entities, solution)

	l8_ds 			= gdal.Open( l8_mosaic )
	l8_proj			= l8_ds.GetProjection()
	assert eo1_proj == l8_proj 
	
	features		= []
	best 			= []
	year			= eo1Scene[10:14]
	doy				= eo1Scene[14:17]
		
	base_dir		= os.path.join(config.ALI_DIR, year, doy, eo1Scene)
	
	best_entropy	= 0
	best_qk			= 0
	best_chip		= 0
	best_minX		= 0
	best_minY		= 0
	best_maxX		= 0
	best_maxY		= 0
	best_samples	= 0
	best_lines 		= 0
	
	footstepPolygon = LoadPolygon(eo1FileName)
	
	for q in qkeys:
		qk		= QuadKey(q)
		bbox	= TileBounds(qk)
	
		minX	= bbox['w']
		maxX	= bbox['e']
		minY	= bbox['s']
		maxY	= bbox['n']

		features.append( Feature(q,minX, maxX, minY, maxY))
			
		minX, maxX, minY, maxY, samples, lines = GetMinMax(l8_ds, bbox)

		within = CheckWithin(qk, minX, maxX, minY, maxY, footstepPolygon)	

		if 1:	#within:
			glsChipSubsetImage	= os.path.join(base_dir, "%s.subset.TIF" % (qk))
			glsChipImage		= os.path.join(base_dir, "%s.TIF" % (qk))
	
			minX, maxX, minY, maxY, e, samples, lines = MakeChip(minX, minY, maxX, maxY, pres, l8_mosaic, glsChipSubsetImage, glsChipImage)
			print "qk", qk, "entropy", e, minX, minY, maxX, maxY, samples, lines
		
		
			#if e > best_entropy:
			#if within and (q == "02010233303"):
			#if (q == "12213002333"):
			if ( e > best_entropy ):
				best_entropy 	= e
				best_qk			= qk
				best_chip		= glsChipImage
				best_minX		= minX
				best_minY		= minY
				best_maxX		= maxX
				best_maxY		= maxY
				best_samples	= samples
				best_lines		= lines
		else:
			print "not within", qk
			
		#print "     chip:", q, minX, minY, maxX, maxY, samples, lines, e
	
	kmlFileName = os.path.join(base_dir, "quadtiles.kml")
	makeKML(features, kmlFileName)

	if best_entropy == 0:
		print "Could not find best tile"
		sys.exit(-1)
			 	
	print "best chip", best_qk, best_chip, best_entropy
	
	l8_ds = None
	
	# So now we need to cut a similar EO-1 Chip
	
	eO1SubsetImage	= os.path.join(base_dir, "eo1_subset.tif")
	eo1ChipImage	= os.path.join(base_dir, "eo1_chip.tif")
	
	print "Making eo1 chip", best_minX, best_minY, best_maxX, best_maxY, pres
	MakeChip(best_minX, best_minY, best_maxX, best_maxY, pres, eo1FileName, eO1SubsetImage, eo1ChipImage)
	print "Made EO1 chip", eo1ChipImage
	
	solution['eo1Chip'] = eo1ChipImage
	solution['refChip'] = best_chip
	solution['qk'] 		= best_qk
	solution['entropy']	= best_entropy
	