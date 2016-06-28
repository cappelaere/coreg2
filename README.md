# Co-Registration of EO-1 with Landsat-8

This code attempts to address significant mis-registration of EO-1 ALI scenes using Landsat-8 latest scenes.

Based on center target latitude and longitude, the software generates up to 9 quadtiles from best landsat scenes available on the AWS cloud or Google storage or USGS (you may need a usgs account/password for that).

The best tile is selected and matched against a similar EO-1 tile.

It is currently using three feature detection algorithms: SIFT, SURF and ORB from OpenCV.
Best one wins.  winner is currently based on number of inliers or matched features.

If it fails, one could try with a lower zoom level (for larger tiles) or try with another reference product such as the one generated with bands 10, 4 and 2 rather than use NVDVI (from band 4 & 5).  This may be more appropriate in the desert.

## Pre-reqs

numpy, scipy, gdal, landsat-util, quadkey, opencv (cv2)

