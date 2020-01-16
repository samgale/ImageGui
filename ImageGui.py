# -*- coding: utf-8 -*-
"""
Image visualization and analysis GUI

Find Allen common coordinate framework data here:
http://help.brain-map.org/display/mouseconnectivity/API
http://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/average_template/
http://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/ara_nissl/
http://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2016/
http://api.brain-map.org/api/v2/structure_graph_download/1.json

@author: samgale
"""

from __future__ import division
import sip
sip.setapi('QString', 2)
import math, os, PIL, time, zipfile
import cv2, nibabel, nrrd, png, tifffile
from xml.dom import minidom
import numpy as np
import scipy.io, scipy.interpolate, scipy.ndimage
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import matplotlib
matplotlib.use('qt5agg')
matplotlib.rcParams['pdf.fonttype'] = 42
import matplotlib.pyplot as plt


def start(data=None,label=None,autoColor=False,mode=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    imageGuiObj = ImageGui(app)
    if data is not None:
        app.processEvents()
        imageGuiObj.fileSavePath = imageGuiObj.fileOpenPath
        if not isinstance(data,list):
            data = [data]
            label = [label]
        elif label is None:
            label = [None]*len(data)
        for d,lab in zip(data,label):
            imageGuiObj.loadImageData(d,lab,autoColor=autoColor)
        if mode=='channels':
            imageGuiObj.setViewChannelsOn()
        elif mode=='3D':
            imageGuiObj.setView3dOn()
    app.exec_()


class ImageGui():
    
    def __init__(self,app):
        self.app = app
        self.fileOpenPath = os.path.dirname(os.path.realpath(__file__))
        self.fileSeriesType = 'Image Series (*.tif *.btf *.png *.jpg *.jp2)'
        self.fileSavePath = None
        self.plotColorOptions = ('Red','Green','Blue','Cyan','Yellow','Magenta','Black','White','Gray')
        self.plotColors = ((1,0,0),(0,1,0),(0,0,1),(0,1,1),(1,1,0),(1,0,1),(0,0,0),(1,1,1),(0.5,0.5,0.5))
        self.numWindows = 4
        self.imageObjs = []
        self.selectedFileIndex = []
        self.checkedFileIndex = [[] for _ in range(self.numWindows)]
        self.selectedWindow = 0
        self.displayedWindows = []
        self.selectedChannels = [[] for _ in range(self.numWindows)]
        self.displayDownsample = [1]*self.numWindows
        self.sliceProjState = [0]*self.numWindows
        self.xyzState = [2]*self.numWindows
        self.ignoreImageRangeChange = False
        self.imageShapeIndex = [(0,1,2) for _ in range(self.numWindows)]
        self.imageShape = [None]*self.numWindows
        self.imageRange = [None]*self.numWindows
        self.imageIndex = [None]*self.numWindows
        self.levelsMax = [255]*self.numWindows
        self.normState = [False]*self.numWindows
        self.showBinaryState = [False]*self.numWindows
        self.stitchState = [False]*self.numWindows
        self.stitchPos = np.full((self.numWindows,1,3),np.nan)
        self.holdStitchRange = [False]*self.numWindows
        self.localAdjustHistory = [[] for _ in range(self.numWindows)]
        self.markedPoints = [None]*self.numWindows
        self.markPointsSize = 5
        self.markPointsColor = (1,1,0)
        self.markPointsColorMap = 'plasma'
        self.markPointsColorValues = [None]*self.numWindows
        self.markPointsColorThresh = [1]*self.numWindows
        self.markPointsStretchFactor = 1
        self.selectedPoints = None
        self.alignRefWindow = [None]*self.numWindows
        self.alignRange = [[None,None] for _ in range(self.numWindows)]
        self.alignAxis = [None]*self.numWindows
        self.alignIndex = [None]*self.numWindows
        self.minContourVertices = 5
        self.contourLineColor = (1,1,0)
        self.atlasTemplate = None
        self.atlasAnnotationData = None
        self.atlasAnnotationRegions = None
        self.atlasLineColor = (1,1,1)
        self.selectedAtlasRegions = [[] for _ in range(self.numWindows)]
        self.selectedAtlasRegionIDs = [[] for _ in range(self.numWindows)]
        
        # main window
        winHeight = 400
        winWidth = 1000
        self.mainWin = QtWidgets.QMainWindow()
        self.mainWin.setWindowTitle('ImageGUI')
        self.mainWin.closeEvent = self.mainWinCloseCallback
        self.mainWin.keyPressEvent = self.mainWinKeyPressCallback
        self.mainWin.resize(winWidth,winHeight)
        screenCenter = QtWidgets.QDesktopWidget().availableGeometry().center()
        mainWinRect = self.mainWin.frameGeometry()
        mainWinRect.moveCenter(screenCenter)
        self.mainWin.move(mainWinRect.topLeft())
        
        # file menu
        self.menuBar = self.mainWin.menuBar()
        self.menuBar.setNativeMenuBar(False)
        self.fileMenu = self.menuBar.addMenu('File')
        self.fileMenuOpen = self.fileMenu.addMenu('Open')
        self.fileMenuOpenFiles = QtWidgets.QAction('File(s)',self.mainWin)
        self.fileMenuOpenFiles.triggered.connect(self.openImageFiles)
        self.fileMenuOpenSeries = QtWidgets.QAction('Image Series',self.mainWin)
        self.fileMenuOpenSeries.triggered.connect(self.openImageSeries)
        self.fileMenuOpen.addActions([self.fileMenuOpenFiles,self.fileMenuOpenSeries])
        
        self.fileMenuSave = self.fileMenu.addMenu('Save')
        self.fileMenuSaveDisplay = QtWidgets.QAction('Display',self.mainWin)
        self.fileMenuSaveDisplay.triggered.connect(self.saveImage)
        self.fileMenuSaveImage = QtWidgets.QAction('Image',self.mainWin)
        self.fileMenuSaveImage.triggered.connect(self.saveImage)
        self.fileMenuSave.addActions([self.fileMenuSaveDisplay,self.fileMenuSaveImage])
        
        self.fileMenuSaveVolume = self.fileMenuSave.addMenu('Volume')
        self.fileMenuSaveVolumeImages = QtWidgets.QAction('Images',self.mainWin)
        self.fileMenuSaveVolumeImages.triggered.connect(self.saveVolume)
        self.fileMenuSaveVolumeMovie = QtWidgets.QAction('Movie',self.mainWin)
        self.fileMenuSaveVolumeMovie.triggered.connect(self.saveVolume)
        self.fileMenuSaveVolumeNpz = QtWidgets.QAction('npz',self.mainWin)
        self.fileMenuSaveVolumeNpz.triggered.connect(self.saveVolume)
        self.fileMenuSaveVolumeMat = QtWidgets.QAction('mat',self.mainWin)
        self.fileMenuSaveVolumeMat.triggered.connect(self.saveVolume)
        self.fileMenuSaveVolume.addActions([self.fileMenuSaveVolumeImages,self.fileMenuSaveVolumeMovie,self.fileMenuSaveVolumeNpz,self.fileMenuSaveVolumeMat])
        
        self.fileMenuPlot = QtWidgets.QAction('Plot',self.mainWin)
        self.fileMenuPlot.triggered.connect(self.plotImage)
        self.fileMenu.addAction(self.fileMenuPlot)
        
        # options menu
        self.optionsMenu = self.menuBar.addMenu('Options')
        self.optionsMenuImportLazy = QtWidgets.QAction('Use lazy/temporary import to save memory',self.mainWin,checkable=True)
        self.optionsMenuImportMemmap = QtWidgets.QAction('Try to import tif and btf files as memmap',self.mainWin,checkable=True)
        self.optionsMenuImportAutoColor = QtWidgets.QAction('Automatically Color Channels During Import',self.mainWin,checkable=True)
        self.optionsMenu.addActions([self.optionsMenuImportLazy,self.optionsMenuImportMemmap,self.optionsMenuImportAutoColor])
        
        self.optionsMenuSetColor = self.optionsMenu.addMenu('Set Color')
        self.optionsMenuSetColorView3dLine = QtWidgets.QAction('View 3D Line',self.mainWin)
        self.optionsMenuSetColorView3dLine.triggered.connect(self.setLineColor)
        self.optionsMenuSetColorPoints = QtWidgets.QAction('Points',self.mainWin)
        self.optionsMenuSetColorPoints.triggered.connect(self.setLineColor)
        self.optionsMenuSetColorContours = QtWidgets.QAction('Contours',self.mainWin)
        self.optionsMenuSetColorContours.triggered.connect(self.setLineColor)
        self.optionsMenuSetColorAtlas = QtWidgets.QAction('Atlas',self.mainWin)
        self.optionsMenuSetColorAtlas.triggered.connect(self.setLineColor)
        self.optionsMenuSetColor.addActions([self.optionsMenuSetColorView3dLine,self.optionsMenuSetColorPoints,self.optionsMenuSetColorContours,self.optionsMenuSetColorAtlas])
        
        # image menu
        self.imageMenu = self.menuBar.addMenu('Image')
        self.imageMenuConvert = self.imageMenu.addMenu('Convert')
        self.imageMenuConvertTo8Bit = QtWidgets.QAction('To 8-Bit',self.mainWin)
        self.imageMenuConvertTo8Bit.triggered.connect(self.convertImage)
        self.imageMenuConvertTo16Bit = QtWidgets.QAction('To 16-Bit',self.mainWin)
        self.imageMenuConvertTo16Bit.triggered.connect(self.convertImage)
        self.imageMenuConvert.addActions([self.imageMenuConvertTo8Bit,self.imageMenuConvertTo16Bit])
        
        self.imageMenuInvert = QtWidgets.QAction('Invert',self.mainWin)
        self.imageMenuInvert.triggered.connect(self.invertImage)
        self.imageMenu.addAction(self.imageMenuInvert)
        
        self.imageMenuNorm = self.imageMenu.addMenu('Normalize')
        self.imageMenuNormImages = QtWidgets.QAction('Images',self.mainWin)
        self.imageMenuNormImages.triggered.connect(self.normalizeImage)
        self.imageMenuNormVolume = QtWidgets.QAction('Volume',self.mainWin)
        self.imageMenuNormVolume.triggered.connect(self.normalizeImage)
        self.imageMenuNorm.addActions([self.imageMenuNormImages,self.imageMenuNormVolume])
        
        self.imageMenuBackground = self.imageMenu.addMenu('Change Background')
        self.imageMenuBackgroundBtoW = QtWidgets.QAction('Black To White',self.mainWin)
        self.imageMenuBackgroundBtoW.triggered.connect(self.changeBackground)
        self.imageMenuBackgroundWtoB = QtWidgets.QAction('White To Black',self.mainWin)
        self.imageMenuBackgroundWtoB.triggered.connect(self.changeBackground)
        self.imageMenuBackground.addActions([self.imageMenuBackgroundBtoW,self.imageMenuBackgroundWtoB])
        
        self.imageMenuRange = self.imageMenu.addMenu('Set Range')
        self.imageMenuRangeLoad = QtWidgets.QAction('Load',self.mainWin)
        self.imageMenuRangeLoad.triggered.connect(self.loadImageRange)
        self.imageMenuRangeSave = QtWidgets.QAction('Save',self.mainWin)
        self.imageMenuRangeSave.triggered.connect(self.saveImageRange)
        self.imageMenuRange.addActions([self.imageMenuRangeLoad,self.imageMenuRangeSave])
        
        self.imageMenuPixelSize = self.imageMenu.addMenu('Set Pixel Size')
        self.imageMenuPixelSizeXY = QtWidgets.QAction('XY',self.mainWin)
        self.imageMenuPixelSizeXY.triggered.connect(self.setPixelSize)
        self.imageMenuPixelSizeZ = QtWidgets.QAction('Z',self.mainWin)
        self.imageMenuPixelSizeZ.triggered.connect(self.setPixelSize)
        self.imageMenuPixelSize.addActions([self.imageMenuPixelSizeXY,self.imageMenuPixelSizeZ])  
        
        self.imageMenuResample = self.imageMenu.addMenu('Resample')
        self.imageMenuResamplePixelSize = QtWidgets.QAction('Using New Pixel Size',self.mainWin)
        self.imageMenuResamplePixelSize.triggered.connect(self.resampleImage)
        self.imageMenuResampleScaleFactor = QtWidgets.QAction('Using Scale Factor',self.mainWin)
        self.imageMenuResampleScaleFactor.triggered.connect(self.resampleImage)
        self.imageMenuResample.addActions([self.imageMenuResamplePixelSize,self.imageMenuResampleScaleFactor])
        
        self.imageMenuFlip = self.imageMenu.addMenu('Flip')
        self.imageMenuFlipImg = self.imageMenuFlip.addMenu('Image')
        self.imageMenuFlipImgHorz = QtWidgets.QAction('Horizontal',self.mainWin)
        self.imageMenuFlipImgHorz.triggered.connect(self.flipImage)
        self.imageMenuFlipImgVert = QtWidgets.QAction('Vertical',self.mainWin)
        self.imageMenuFlipImgVert.triggered.connect(self.flipImage)
        self.imageMenuFlipImg.addActions([self.imageMenuFlipImgHorz,self.imageMenuFlipImgVert])
        self.imageMenuFlipVol = self.imageMenuFlip.addMenu('Volume')
        self.imageMenuFlipVolX = QtWidgets.QAction('X',self.mainWin)
        self.imageMenuFlipVolX.triggered.connect(self.flipImage)
        self.imageMenuFlipVolY = QtWidgets.QAction('Y',self.mainWin)
        self.imageMenuFlipVolY.triggered.connect(self.flipImage)
        self.imageMenuFlipVolZ = QtWidgets.QAction('Z',self.mainWin)
        self.imageMenuFlipVolZ.triggered.connect(self.flipImage)
        self.imageMenuFlipVol.addActions([self.imageMenuFlipVolX,self.imageMenuFlipVolY,self.imageMenuFlipVolZ])
        
        self.imageMenuRotate = self.imageMenu.addMenu('Rotate')
        self.imageMenuRotate90C = QtWidgets.QAction('90 Deg Clockwise',self.mainWin)
        self.imageMenuRotate90C.triggered.connect(self.rotateImage)
        self.imageMenuRotate90CC = QtWidgets.QAction('90 Deg Counter-Clockwise',self.mainWin)
        self.imageMenuRotate90CC.triggered.connect(self.rotateImage)
        self.imageMenuRotateAngle = QtWidgets.QAction('Angle',self.mainWin)
        self.imageMenuRotateAngle.triggered.connect(self.rotateImage)
        self.imageMenuRotateLine = QtWidgets.QAction('To Line',self.mainWin)
        self.imageMenuRotateLine.triggered.connect(self.rotateImage)
        self.imageMenuRotate.addActions([self.imageMenuRotate90C,self.imageMenuRotate90CC,self.imageMenuRotateAngle,self.imageMenuRotateLine])
        
        self.imageMenuSaveOffsets = QtWidgets.QAction('Save Offsets',self.mainWin)
        self.imageMenuSaveOffsets.triggered.connect(self.saveOffsets)
        self.imageMenu.addAction(self.imageMenuSaveOffsets)
        
        self.imageMenuStitch = self.imageMenu.addMenu('Stitch')
        self.imageMenuStitchOverlay = self.imageMenuStitch.addMenu('Overlay')
        self.imageMenuStitchOverlayMax = QtWidgets.QAction('Max',self.mainWin,checkable=True)
        self.imageMenuStitchOverlayMax.setChecked(True)
        self.imageMenuStitchOverlayMax.triggered.connect(self.setStitchOverlayMode)
        self.imageMenuStitchOverlayReplace = QtWidgets.QAction('Replace',self.mainWin,checkable=True)
        self.imageMenuStitchOverlayReplace.triggered.connect(self.setStitchOverlayMode)
        self.imageMenuStitchOverlay.addActions([self.imageMenuStitchOverlayMax,self.imageMenuStitchOverlayReplace])
        
        self.imageMenuStitchTile = self.imageMenuStitch.addMenu('Tile')
        self.imageMenuStitchTileXY = QtWidgets.QAction('XY',self.mainWin,checkable=True)
        self.imageMenuStitchTileXY.setChecked(True)
        self.imageMenuStitchTileXY.triggered.connect(self.setStitchTileMode)
        self.imageMenuStitchTileZ = QtWidgets.QAction('Z',self.mainWin,checkable=True)
        self.imageMenuStitchTileZ.triggered.connect(self.setStitchTileMode)
        self.imageMenuStitchTile.addActions([self.imageMenuStitchTileXY,self.imageMenuStitchTileZ])        
        
        self.imageMenuStitchLoad = QtWidgets.QAction('Load Postions',self.mainWin)
        self.imageMenuStitchLoad.triggered.connect(self.loadStitchPositions)
        self.imageMenuStitchSave = QtWidgets.QAction('Save Postions',self.mainWin)
        self.imageMenuStitchSave.triggered.connect(self.saveStitchPositions)
        self.imageMenuStitch.addActions([self.imageMenuStitchLoad,self.imageMenuStitchSave])
        
        self.imageMenuLocalAdjust = self.imageMenu.addMenu('Local Adjustments')
        self.imageMenuLocalAdjustClear = QtWidgets.QAction('Clear History',self.mainWin)
        self.imageMenuLocalAdjustClear.triggered.connect(self.clearLocalAdjustHistory)
        self.imageMenuLocalAdjustSave = QtWidgets.QAction('Save History',self.mainWin)
        self.imageMenuLocalAdjustSave.triggered.connect(self.saveLocalAdjustHistory)
        self.imageMenuLocalAdjustLoad = QtWidgets.QAction('Load and Apply',self.mainWin)
        self.imageMenuLocalAdjustLoad.triggered.connect(self.loadLocalAdjust)
        self.imageMenuLocalAdjust.addActions([self.imageMenuLocalAdjustClear,self.imageMenuLocalAdjustSave,self.imageMenuLocalAdjustLoad])
        
        self.imageMenuTransform = self.imageMenu.addMenu('Transform')
        self.imageMenuTransformAligned = QtWidgets.QAction('Transform Aligned',self.mainWin)
        self.imageMenuTransformAligned.triggered.connect(self.transformImage)
        self.imageMenuTransformLoad = QtWidgets.QAction('Load Transform Matrix',self.mainWin)
        self.imageMenuTransformLoad.triggered.connect(self.transformImage)
        self.imageMenuTransformSave = QtWidgets.QAction('Save Transform Matrix',self.mainWin)
        self.imageMenuTransformSave.triggered.connect(self.saveTransformMatrix)
        self.imageMenuTransform.addActions([self.imageMenuTransformAligned,self.imageMenuTransformLoad,self.imageMenuTransformSave])
        
        self.imageMenuWarp = QtWidgets.QAction('Warp',self.mainWin)
        self.imageMenuWarp.triggered.connect(self.warpImage)
        self.imageMenu.addAction(self.imageMenuWarp)
    
        self.imageMenuMakeCCF = self.imageMenu.addMenu('Make CCF Volume')
        self.imageMenuMakeCCFNoIntp = QtWidgets.QAction('No Interpolation',self.mainWin)
        self.imageMenuMakeCCFNoIntp.triggered.connect(self.makeCCFVolume)
        self.imageMenuMakeCCFIntp = QtWidgets.QAction('Interpolate Z',self.mainWin)
        self.imageMenuMakeCCFIntp.triggered.connect(self.makeCCFVolume)
        self.imageMenuMakeCCF.addActions([self.imageMenuMakeCCFNoIntp,self.imageMenuMakeCCFIntp])        
        
        # analysis menu
        self.analysisMenu = self.menuBar.addMenu('Analysis')
        self.analysisMenuPoints = self.analysisMenu.addMenu('Points')
        
        self.analysisMenuPointsLock = QtWidgets.QAction('Lock',self.mainWin,checkable=True)
        self.analysisMenuPointsJitter = QtWidgets.QAction('Jitter',self.mainWin,checkable=True)
        self.analysisMenuPointsJitter.triggered.connect(self.jitterPoints)
        self.analysisMenuPoints.addActions([self.analysisMenuPointsLock,self.analysisMenuPointsJitter])
        
        self.analysisMenuPointsLine = self.analysisMenuPoints.addMenu('Line')
        self.analysisMenuPointsLineNone = QtWidgets.QAction('None',self.mainWin,checkable=True)
        self.analysisMenuPointsLineNone.setChecked(True)
        self.analysisMenuPointsLineNone.triggered.connect(self.setMarkedPointsLineStyle)
        self.analysisMenuPointsLineLine = QtWidgets.QAction('Line',self.mainWin,checkable=True)
        self.analysisMenuPointsLineLine.triggered.connect(self.setMarkedPointsLineStyle)
        self.analysisMenuPointsLinePoly = QtWidgets.QAction('Polygon',self.mainWin,checkable=True)
        self.analysisMenuPointsLinePoly.triggered.connect(self.setMarkedPointsLineStyle)
        self.analysisMenuPointsLine.addActions([self.analysisMenuPointsLineNone,self.analysisMenuPointsLineLine,self.analysisMenuPointsLinePoly])
        
        self.analysisMenuPointsDraw = self.analysisMenuPoints.addMenu('Draw')
        self.analysisMenuPointsDrawLine = QtWidgets.QAction('Line',self.mainWin)
        self.analysisMenuPointsDrawLine.triggered.connect(self.drawLines)
        self.analysisMenuPointsDrawPoly = QtWidgets.QAction('Polygon',self.mainWin)
        self.analysisMenuPointsDrawPoly.triggered.connect(self.drawLines)
        self.analysisMenuPointsDrawTri = QtWidgets.QAction('Delauney Triangles',self.mainWin)
        self.analysisMenuPointsDrawTri.triggered.connect(self.drawLines)
        self.analysisMenuPointsDraw.addActions([self.analysisMenuPointsDrawLine,self.analysisMenuPointsDrawPoly,self.analysisMenuPointsDrawTri])

        self.analysisMenuPointsCopy = self.analysisMenuPoints.addMenu('Copy')
        self.analysisMenuPointsCopyFlip = QtWidgets.QAction('Flip Horizontal',self.mainWin)
        self.analysisMenuPointsCopyFlip.triggered.connect(self.copyPoints)
        self.analysisMenuPointsCopyPrevious = QtWidgets.QAction('From Previous Image',self.mainWin)
        self.analysisMenuPointsCopyPrevious.triggered.connect(self.copyPoints)
        self.analysisMenuPointsCopyNext = QtWidgets.QAction('From Next Image',self.mainWin)
        self.analysisMenuPointsCopyNext.triggered.connect(self.copyPoints)
        self.analysisMenuPointsCopyAlignedImg = QtWidgets.QAction('From Aligned Image',self.mainWin)
        self.analysisMenuPointsCopyAlignedImg.triggered.connect(self.copyRefPoints)
        self.analysisMenuPointsCopyAlignedVol = QtWidgets.QAction('From Aligned Volume',self.mainWin)
        self.analysisMenuPointsCopyAlignedVol.triggered.connect(self.copyRefPoints)
        self.analysisMenuPointsCopy.addActions([self.analysisMenuPointsCopyFlip,self.analysisMenuPointsCopyPrevious,self.analysisMenuPointsCopyNext,self.analysisMenuPointsCopyAlignedImg,self.analysisMenuPointsCopyAlignedVol])
        
        self.analysisMenuPointsLoad = QtWidgets.QAction('Load',self.mainWin)
        self.analysisMenuPointsLoad.triggered.connect(self.loadPoints)
        self.analysisMenuPointsSave = QtWidgets.QAction('Save',self.mainWin)
        self.analysisMenuPointsSave.triggered.connect(self.savePoints)
        self.analysisMenuPointsClear = QtWidgets.QAction('Clear',self.mainWin)
        self.analysisMenuPointsClear.triggered.connect(self.clearPoints)
        self.analysisMenuPoints.addActions([self.analysisMenuPointsLoad,self.analysisMenuPointsSave,self.analysisMenuPointsClear])
        
        self.analysisMenuPointsSetColorMap = QtWidgets.QAction('Set Color Map',self.mainWin)
        self.analysisMenuPointsSetColorMap.triggered.connect(self.setPointsColorMap)
        self.analysisMenuPointsSetColorThresh = QtWidgets.QAction('Set Color Threshold',self.mainWin)
        self.analysisMenuPointsSetColorThresh.triggered.connect(self.setPointsColorThresh)
        self.analysisMenuPointsApplyColorMap = QtWidgets.QAction('Apply Color Map',self.mainWin)
        self.analysisMenuPointsApplyColorMap.triggered.connect(self.applyPointsColorMap)
        self.analysisMenuPoints.addActions([self.analysisMenuPointsSetColorMap,self.analysisMenuPointsSetColorThresh,self.analysisMenuPointsApplyColorMap])
        
        self.analysisMenuPointsStretch = QtWidgets.QAction('Set Stretch Factor',self.mainWin)
        self.analysisMenuPointsStretch.triggered.connect(self.setPointsStretchFactor)
        self.analysisMenuPoints.addAction(self.analysisMenuPointsStretch)
        
        self.analysisMenuContours = self.analysisMenu.addMenu('Contours')
        self.analysisMenuContoursFind = self.analysisMenuContours.addMenu('Find')
        self.analysisMenuContoursFindContours = QtWidgets.QAction('Contours',self.mainWin)
        self.analysisMenuContoursFindContours.triggered.connect(self.getContours)
        self.analysisMenuContoursFindConvexHull = QtWidgets.QAction('Convex Hull',self.mainWin)
        self.analysisMenuContoursFindConvexHull.triggered.connect(self.getContours)
        self.analysisMenuContoursFindRectangle = QtWidgets.QAction('Bounding Rectangle',self.mainWin)
        self.analysisMenuContoursFindRectangle.triggered.connect(self.getContours)
        self.analysisMenuContoursFind.addActions([self.analysisMenuContoursFindContours,self.analysisMenuContoursFindConvexHull,self.analysisMenuContoursFindRectangle])
        
        self.analysisMenuContoursMerge = self.analysisMenuContours.addMenu('Merge')
        self.analysisMenuContoursMergeHorz = QtWidgets.QAction('Horizontal',self.mainWin,checkable=True)
        self.analysisMenuContoursMergeHorz.triggered.connect(self.setMergeContours)
        self.analysisMenuContoursMergeVert = QtWidgets.QAction('Vertical',self.mainWin,checkable=True)
        self.analysisMenuContoursMergeVert.triggered.connect(self.setMergeContours)
        self.analysisMenuContoursMerge.addActions([self.analysisMenuContoursMergeHorz,self.analysisMenuContoursMergeVert])
        
        self.analysisMenuContoursFill = QtWidgets.QAction('Show Filled',self.mainWin,checkable=True)
        self.analysisMenuContoursMinVertices = QtWidgets.QAction('Minimum Vertices',self.mainWin)
        self.analysisMenuContoursMinVertices.triggered.connect(self.setMinContourVertices)
        self.analysisMenuContoursSave = QtWidgets.QAction('Save ROIs as Images',self.mainWin)
        self.analysisMenuContoursSave.triggered.connect(self.saveContours)
        self.analysisMenuContours.addActions([self.analysisMenuContoursFill,self.analysisMenuContoursMinVertices,self.analysisMenuContoursSave])
        
        # atlas menu
        self.atlasMenu = self.menuBar.addMenu('Atlas')
        self.atlasMenuLoad = QtWidgets.QAction('Load Template',self.mainWin)
        self.atlasMenuLoad.triggered.connect(self.loadAtlasTemplate)
        self.atlasMenu.addAction(self.atlasMenuLoad)
        
        self.atlasMenuSelect = self.atlasMenu.addMenu('Select Regions')
        self.atlasRegionLabels = ('MRN','SCs','LGd','LGv','LP','LD','VISa','VISal','VISam','VISl','VISli','VISp','VISpl','VISpm','VISpor','VISrl','ACA','ORB','RSP','CLA','LA','BLA','Isocortex')
        self.atlasRegionMenu = []
        for region in self.atlasRegionLabels:
            self.atlasRegionMenu.append(QtWidgets.QAction(region,self.mainWin,checkable=True))
            self.atlasRegionMenu[-1].triggered.connect(self.setAtlasRegions)
        self.atlasMenuSelect.addActions(self.atlasRegionMenu)
        
        self.atlasMenuClear = QtWidgets.QAction('Clear All',self.mainWin)
        self.atlasMenuClear.triggered.connect(self.clearAtlasRegions)
        self.atlasMenu.addAction(self.atlasMenuClear)
        
        self.atlasMenuHemi = self.atlasMenu.addMenu('Hemisphere')
        self.atlasMenuHemiBoth = QtWidgets.QAction('Both',self.mainWin,checkable=True)
        self.atlasMenuHemiBoth.setChecked(True)
        self.atlasMenuHemiBoth.triggered.connect(self.setAtlasHemi)
        self.atlasMenuHemiLeft = QtWidgets.QAction('Left',self.mainWin,checkable=True)
        self.atlasMenuHemiLeft.triggered.connect(self.setAtlasHemi)
        self.atlasMenuHemiRight = QtWidgets.QAction('Right',self.mainWin,checkable=True)
        self.atlasMenuHemiRight.triggered.connect(self.setAtlasHemi)
        self.atlasMenuHemi.addActions([self.atlasMenuHemiBoth,self.atlasMenuHemiLeft,self.atlasMenuHemiRight])
        
        self.atlasRotateAnnotation = QtWidgets.QAction('Rotate Annotation Data',self.mainWin)
        self.atlasRotateAnnotation.triggered.connect(self.rotateAnnotationData)
        self.atlasResetAnnotation = QtWidgets.QAction('Reset Annotation Data',self.mainWin)
        self.atlasResetAnnotation.triggered.connect(self.resetAnnotationData)
        self.atlasMenuNorm = QtWidgets.QAction('Normalize Region Levels',self.mainWin)
        self.atlasMenuNorm.triggered.connect(self.normRegionLevels)
        self.atlasMenuZero = QtWidgets.QAction('Set Zero Outside Region',self.mainWin)
        self.atlasMenuZero.triggered.connect(self.setOutsideRegionZero)
        self.atlasMenu.addActions([self.atlasRotateAnnotation,self.atlasResetAnnotation,self.atlasMenuNorm,self.atlasMenuZero])
        
        # image windows
        self.imageLayout = pg.GraphicsLayoutWidget()
        self.imageLayoutResizeFcn = self.imageLayout.resizeEvent
        self.imageLayout.resizeEvent = self.imageLayoutResizeCallback
        self.imageViewBox = [pg.ViewBox(invertY=True,enableMouse=False,enableMenu=False) for _ in range(self.numWindows)]
        self.imageItem = [pg.ImageItem() for _ in range(self.numWindows)]
        self.markPointsPlot = [pg.PlotDataItem(x=[],y=[],symbol='o',symbolBrush=None,pen=None) for _ in range(self.numWindows)]
        clickCallbacks = (self.window1ClickCallback,self.window2ClickCallback,self.window3ClickCallback,self.window4ClickCallback)
        doubleClickCallbacks = (self.window1DoubleClickCallback,self.window2DoubleClickCallback,self.window3DoubleClickCallback,self.window4DoubleClickCallback)
        for viewBox,imgItem,ptsPlot,click,doubleClick in reversed(tuple(zip(self.imageViewBox,self.imageItem,self.markPointsPlot,clickCallbacks,doubleClickCallbacks))):
            self.imageLayout.addItem(viewBox)
            viewBox.addItem(imgItem)
            viewBox.addItem(ptsPlot)
            viewBox.sigRangeChanged.connect(self.imageRangeChanged)
            imgItem.mouseClickEvent = click
            imgItem.mouseDoubleClickEvent = doubleClick
        
        self.view3dSliceLines = [[pg.InfiniteLine(pos=0,angle=angle,pen='r',movable=True) for angle in (0,90)] for _ in range(3)]
        for windowLines in self.view3dSliceLines:
            for line in windowLines:
                line.sigDragged.connect(self.view3dSliceLineDragged)
        
        # file selection
        self.fileListbox = QtWidgets.QListWidget()
        self.fileListbox.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.fileListbox.itemSelectionChanged.connect(self.fileListboxSelectionCallback)
        self.fileListbox.itemClicked.connect(self.fileListboxItemClickedCallback)
        
        self.moveFileDownButton = QtWidgets.QToolButton()
        self.moveFileDownButton.setArrowType(QtCore.Qt.DownArrow)
        self.moveFileDownButton.clicked.connect(self.moveFileDownButtonCallback)
        
        self.moveFileUpButton = QtWidgets.QToolButton()
        self.moveFileUpButton.setArrowType(QtCore.Qt.UpArrow)
        self.moveFileUpButton.clicked.connect(self.moveFileUpButtonCallback)
        
        self.removeFileButton = QtWidgets.QPushButton('Remove')
        self.removeFileButton.clicked.connect(self.removeFileButtonCallback)
        
        self.stitchCheckbox = QtWidgets.QCheckBox('Stitch')
        self.stitchCheckbox.clicked.connect(self.stitchCheckboxCallback)
        
        self.fileSelectLayout = QtWidgets.QGridLayout()
        self.fileSelectLayout.addWidget(self.moveFileDownButton,0,0,1,1)
        self.fileSelectLayout.addWidget(self.moveFileUpButton,0,1,1,1)
        self.fileSelectLayout.addWidget(self.removeFileButton,0,2,1,2)
        self.fileSelectLayout.addWidget(self.stitchCheckbox,0,8,1,2)
        self.fileSelectLayout.addWidget(self.fileListbox,1,0,9,10)
        
        # window and channel selection
        self.windowListbox = QtWidgets.QListWidget()
        self.windowListbox.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.windowListbox.addItems(['Window '+str(n+1) for n in range(self.numWindows)])
        self.windowListbox.setCurrentRow(0)
        self.windowListbox.itemSelectionChanged.connect(self.windowListboxCallback)
        
        self.linkWindowsCheckbox = QtWidgets.QCheckBox('Link Windows')
        self.linkWindowsCheckbox.clicked.connect(self.linkWindowsCheckboxCallback)
        
        self.channelListbox = QtWidgets.QListWidget()
        self.channelListbox.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.channelListbox.itemSelectionChanged.connect(self.channelListboxCallback)
        
        self.channelColorMenu = QtWidgets.QComboBox()
        self.channelColorMenu.addItems(('Channel Color','Gray','Red','Green','Blue','Magenta'))
        self.channelColorMenu.currentIndexChanged.connect(self.channelColorMenuCallback)
        
        self.windowChannelLayout = QtWidgets.QGridLayout()
        self.windowChannelLayout.addWidget(self.linkWindowsCheckbox,0,0,1,1)
        self.windowChannelLayout.addWidget(self.windowListbox,1,0,4,1) 
        self.windowChannelLayout.addWidget(self.channelColorMenu,0,2,1,1)
        self.windowChannelLayout.addWidget(self.channelListbox,1,2,4,1)
        
        # view control
        self.downsampleLabel = QtWidgets.QLabel('Display Downsample Interval')
        self.downsampleEdit = QtWidgets.QLineEdit('1')
        self.downsampleEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.downsampleEdit.editingFinished.connect(self.downsampleEditCallback)
        
        self.imageDimensionsLabel = QtWidgets.QLabel('XYZ Dimensions: ')
        self.imagePixelSizeLabel = QtWidgets.QLabel('XYZ Pixel Size (\u03BCm): ')        
        
        self.sliceButton = QtWidgets.QRadioButton('Slice')
        self.sliceButton.setChecked(True)
        self.projectionButton = QtWidgets.QRadioButton('Projection')
        self.sliceProjButtons = (self.sliceButton,self.projectionButton)
        self.sliceProjGroupLayout = QtWidgets.QVBoxLayout()
        for button in self.sliceProjButtons:
            button.clicked.connect(self.sliceProjButtonCallback)
            self.sliceProjGroupLayout.addWidget(button)
        self.sliceProjGroupBox = QtWidgets.QGroupBox()
        self.sliceProjGroupBox.setLayout(self.sliceProjGroupLayout)
        
        self.xButton = QtWidgets.QRadioButton('X')
        self.yButton = QtWidgets.QRadioButton('Y')
        self.zButton = QtWidgets.QRadioButton('Z')
        self.zButton.setChecked(True)
        self.xyzButtons = (self.xButton,self.yButton,self.zButton)
        self.xyzGroupLayout = QtWidgets.QVBoxLayout()
        for button in self.xyzButtons:
            button.clicked.connect(self.xyzButtonCallback)
            self.xyzGroupLayout.addWidget(button)
        self.xyzGroupBox = QtWidgets.QGroupBox()
        self.xyzGroupBox.setLayout(self.xyzGroupLayout)
        
        self.viewChannelsCheckbox = QtWidgets.QCheckBox('Channel View')
        self.viewChannelsCheckbox.clicked.connect(self.viewChannelsCheckboxCallback)
        
        self.view3dCheckbox = QtWidgets.QCheckBox('3D View')
        self.view3dCheckbox.clicked.connect(self.view3dCheckboxCallback)
        
        self.viewControlLayout = QtWidgets.QGridLayout()
        self.viewControlLayout.addWidget(self.downsampleLabel,0,0,1,2)
        self.viewControlLayout.addWidget(self.downsampleEdit,0,2,1,1)
        self.viewControlLayout.addWidget(self.imageDimensionsLabel,1,0,1,3)
        self.viewControlLayout.addWidget(self.imagePixelSizeLabel,2,0,1,3)
        self.viewControlLayout.addWidget(self.viewChannelsCheckbox,3,0,1,1)
        self.viewControlLayout.addWidget(self.view3dCheckbox,3,1,1,1)
        self.viewControlLayout.addWidget(self.sliceProjGroupBox,4,0,2,2)
        self.viewControlLayout.addWidget(self.xyzGroupBox,3,2,3,1)
        
        # range control 
        self.zoomPanButton = QtWidgets.QPushButton('Zoom/Pan',checkable=True)
        self.zoomPanButton.clicked.connect(self.zoomPanButtonCallback)

        self.roiButton = QtWidgets.QPushButton('ROI',checkable=True)
        self.roiButton.clicked.connect(self.roiButtonCallback)         
        
        self.resetViewButton = QtWidgets.QPushButton('Reset View')
        self.resetViewButton.clicked.connect(self.resetViewButtonCallback)
        
        self.rangeViewLabel = QtWidgets.QLabel('View')
        self.rangeMinLabel = QtWidgets.QLabel('Min')
        self.rangeMaxLabel = QtWidgets.QLabel('Max')
        for label in (self.rangeViewLabel,self.rangeMinLabel,self.rangeMaxLabel):
            label.setAlignment(QtCore.Qt.AlignHCenter)
        
        self.xRangeLabel = QtWidgets.QLabel('X')
        self.yRangeLabel = QtWidgets.QLabel('Y')
        self.zRangeLabel = QtWidgets.QLabel('Z')
        
        self.xImageNumEdit = QtWidgets.QLineEdit('')
        self.yImageNumEdit = QtWidgets.QLineEdit('')
        self.zImageNumEdit = QtWidgets.QLineEdit('')
        self.imageNumEditBoxes = (self.yImageNumEdit,self.xImageNumEdit,self.zImageNumEdit)
        for editBox in self.imageNumEditBoxes:
            editBox.setAlignment(QtCore.Qt.AlignHCenter)
            editBox.editingFinished.connect(self.imageNumEditCallback)
        
        self.xRangeMinEdit = QtWidgets.QLineEdit('')
        self.xRangeMaxEdit = QtWidgets.QLineEdit('')
        self.yRangeMinEdit = QtWidgets.QLineEdit('')
        self.yRangeMaxEdit = QtWidgets.QLineEdit('')
        self.zRangeMinEdit = QtWidgets.QLineEdit('')
        self.zRangeMaxEdit = QtWidgets.QLineEdit('')
        self.rangeEditBoxes = ((self.yRangeMinEdit,self.yRangeMaxEdit),(self.xRangeMinEdit,self.xRangeMaxEdit),(self.zRangeMinEdit,self.zRangeMaxEdit))
        for editBox in (box for boxes in self.rangeEditBoxes for box in boxes):
            editBox.setAlignment(QtCore.Qt.AlignHCenter)
            editBox.editingFinished.connect(self.rangeEditCallback)
        
        self.rangeControlLayout = QtWidgets.QGridLayout()
        self.rangeControlLayout.addWidget(self.zoomPanButton,0,0,1,4)
        self.rangeControlLayout.addWidget(self.roiButton,0,4,1,4)
        self.rangeControlLayout.addWidget(self.resetViewButton,0,8,1,4)
        self.rangeControlLayout.addWidget(self.rangeViewLabel,1,3,1,3)
        self.rangeControlLayout.addWidget(self.rangeMinLabel,1,6,1,3)
        self.rangeControlLayout.addWidget(self.rangeMaxLabel,1,9,1,3)
        self.rangeControlLayout.addWidget(self.xRangeLabel,2,0,1,3)
        self.rangeControlLayout.addWidget(self.xImageNumEdit,2,3,1,3)
        self.rangeControlLayout.addWidget(self.xRangeMinEdit,2,6,1,3)
        self.rangeControlLayout.addWidget(self.xRangeMaxEdit,2,9,1,3)
        self.rangeControlLayout.addWidget(self.yRangeLabel,3,0,1,3)
        self.rangeControlLayout.addWidget(self.yImageNumEdit,3,3,1,3)
        self.rangeControlLayout.addWidget(self.yRangeMinEdit,3,6,1,3)
        self.rangeControlLayout.addWidget(self.yRangeMaxEdit,3,9,1,3)
        self.rangeControlLayout.addWidget(self.zRangeLabel,4,0,1,3)
        self.rangeControlLayout.addWidget(self.zImageNumEdit,4,3,1,3)
        self.rangeControlLayout.addWidget(self.zRangeMinEdit,4,6,1,3)
        self.rangeControlLayout.addWidget(self.zRangeMaxEdit,4,9,1,3)
                
        # levels plot
        self.levelsPlotWidget = pg.PlotWidget(enableMenu=False)
        self.levelsPlotItem = self.levelsPlotWidget.getPlotItem()
        self.levelsPlotItem.setMouseEnabled(x=False,y=False)
        self.levelsPlotItem.hideButtons()
        self.levelsPlotItem.setLabel('left','log(# Pixels)')
        self.levelsPlotItem.setLabel('bottom','Intensity')
        self.levelsPlotItem.getAxis('left').setTicks([[(0,'0')],[]])
        self.levelsPlotItem.getAxis('bottom').setTicks([[(0,'0'),(100,'100'),(200,'200')],[]])
        self.levelsPlotItem.setXRange(0,255)
        self.levelsPlot = self.levelsPlotItem.plot(x=[],y=[])
        self.lowLevelLine = pg.InfiniteLine(pos=0,pen='r',movable=True,bounds=(0,254))
        self.lowLevelLine.sigPositionChangeFinished.connect(self.lowLevelLineCallback)
        self.levelsPlotItem.addItem(self.lowLevelLine)
        self.highLevelLine = pg.InfiniteLine(pos=255,pen='r',movable=True,bounds=(1,255))
        self.highLevelLine.sigPositionChangeFinished.connect(self.highLevelLineCallback)
        self.levelsPlotItem.addItem(self.highLevelLine)
        
        # levels control
        self.showNoLevelsButton = QtWidgets.QRadioButton('None')
        self.showNoLevelsButton.setChecked(True)
        self.showVolumeLevelsButton = QtWidgets.QRadioButton('Volume')
        self.showImageLevelsButton = QtWidgets.QRadioButton('Image')
        self.showLevelsGroupLayout = QtWidgets.QHBoxLayout()
        for button in (self.showNoLevelsButton,self.showVolumeLevelsButton,self.showImageLevelsButton):
            button.clicked.connect(self.showLevelsButtonCallback)
            self.showLevelsGroupLayout.addWidget(button)
        self.showLevelsGroupBox = QtWidgets.QGroupBox()
        self.showLevelsGroupBox.setLayout(self.showLevelsGroupLayout)
        self.showLevelsGroupBox.setMinimumWidth(10)
        self.showLevelsGroupBox.setMinimumWidth(125)
        
        self.lowLevelBox = QtWidgets.QSpinBox()
        self.lowLevelBox.setPrefix('Low Level:  ')
        self.lowLevelBox.setRange(0,254)
        self.lowLevelBox.setSingleStep(1)
        self.lowLevelBox.setValue(0)
        self.lowLevelBox.valueChanged.connect(self.lowLevelBoxCallback)
        
        self.highLevelBox = QtWidgets.QSpinBox()
        self.highLevelBox.setPrefix('High Level:  ')
        self.highLevelBox.setRange(1,255)
        self.highLevelBox.setSingleStep(1)
        self.highLevelBox.setValue(255)
        self.highLevelBox.valueChanged.connect(self.highLevelBoxCallback)
        
        self.gammaBox = QtWidgets.QDoubleSpinBox()
        self.gammaBox.setPrefix('Gamma:  ')
        self.gammaBox.setDecimals(2)
        self.gammaBox.setRange(0.05,3)
        self.gammaBox.setSingleStep(0.01)
        self.gammaBox.setValue(1)
        self.gammaBox.valueChanged.connect(self.gammaBoxCallback)
        
        self.alphaBox = QtWidgets.QDoubleSpinBox()
        self.alphaBox.setPrefix('Alpha:  ')
        self.alphaBox.setDecimals(2)
        self.alphaBox.setRange(0,1)
        self.alphaBox.setSingleStep(0.01)
        self.alphaBox.setValue(1)
        self.alphaBox.valueChanged.connect(self.alphaBoxCallback)
        
        self.levelsBoxes = (self.lowLevelBox,self.highLevelBox,self.gammaBox,self.alphaBox)
        
        self.resetLevelsButton = QtWidgets.QPushButton('Reset Levels')
        self.resetLevelsButton.clicked.connect(self.resetLevelsButtonCallback)
        
        self.normDisplayCheckbox = QtWidgets.QCheckBox('Normalize Display')
        self.normDisplayCheckbox.clicked.connect(self.normDisplayCheckboxCallback)
        
        self.showBinaryCheckbox = QtWidgets.QCheckBox('Show Binary Image')
        self.showBinaryCheckbox.clicked.connect(self.showBinaryCheckboxCallback)
        
        self.levelsControlLayout = QtWidgets.QGridLayout()
        self.levelsControlLayout.addWidget(self.showLevelsGroupBox,0,0,1,2)
        self.levelsControlLayout.addWidget(self.lowLevelBox,1,0,1,1)
        self.levelsControlLayout.addWidget(self.highLevelBox,1,1,1,1)
        self.levelsControlLayout.addWidget(self.gammaBox,2,0,1,1)
        self.levelsControlLayout.addWidget(self.alphaBox,2,1,1,1)
        self.levelsControlLayout.addWidget(self.resetLevelsButton,3,0,1,1)
        self.levelsControlLayout.addWidget(self.normDisplayCheckbox,3,1,1,1)
        self.levelsControlLayout.addWidget(self.showBinaryCheckbox,4,1,1,1)
        
        # mark points tab        
        self.markPointsTable = QtWidgets.QTableWidget(1,3)
        self.markPointsTable.resizeEvent = self.markPointsTableResizeCallback
        self.markPointsTable.keyPressEvent = self.markPointsTableKeyPressCallback
        self.markPointsTable.itemSelectionChanged.connect(self.markPointsTableSelectionCallback)
        self.markPointsTable.setHorizontalHeaderLabels(['X','Y','Z'])
        for col in range(3):
            item = QtWidgets.QTableWidgetItem('')
            item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.markPointsTable.setItem(0,col,item)
        self.markPointsLayout = QtWidgets.QGridLayout()
        self.markPointsLayout.addWidget(self.markPointsTable,0,0,1,1)
        self.markPointsTab = QtWidgets.QWidget()
        self.markPointsTab.setLayout(self.markPointsLayout)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.markPointsTab,'Mark Points')
        
        # align tab
        self.alignRefLabel = QtWidgets.QLabel('Reference')
        self.alignRefMenu = QtWidgets.QComboBox()
        self.alignRefMenu.addItems(['Window '+str(n+1) for n in range(self.numWindows)])
        self.alignRefMenu.setCurrentIndex(0)
        
        self.alignStartLabel = QtWidgets.QLabel('Start')
        self.alignStartEdit = QtWidgets.QLineEdit('')
        self.alignStartEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.alignStartEdit.editingFinished.connect(self.alignStartEditCallback)
        
        self.alignEndLabel = QtWidgets.QLabel('End')
        self.alignEndEdit = QtWidgets.QLineEdit('')
        self.alignEndEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.alignEndEdit.editingFinished.connect(self.alignEndEditCallback)
        
        self.alignCheckbox = QtWidgets.QCheckBox('Align')
        self.alignCheckbox.clicked.connect(self.alignCheckboxCallback)
        
        self.alignLayout = QtWidgets.QGridLayout()
        self.alignLayout.addWidget(self.alignRefLabel,0,0,1,1)
        self.alignLayout.addWidget(self.alignRefMenu,0,1,1,1)
        self.alignLayout.addWidget(self.alignStartLabel,1,0,1,1)
        self.alignLayout.addWidget(self.alignStartEdit,1,1,1,1)
        self.alignLayout.addWidget(self.alignEndLabel,2,0,1,1)
        self.alignLayout.addWidget(self.alignEndEdit,2,1,1,1)
        self.alignLayout.addWidget(self.alignCheckbox,3,1,1,1)
        self.alignTab = QtWidgets.QWidget()
        self.alignTab.setLayout(self.alignLayout)
        self.tabs.addTab(self.alignTab,'Align')
        
        # main layout
        self.mainWidget = QtWidgets.QWidget()
        self.mainWin.setCentralWidget(self.mainWidget)
        self.mainLayout = QtWidgets.QGridLayout()
        setLayoutGridSpacing(self.mainLayout,winHeight,winWidth,4,4)
        self.mainWidget.setLayout(self.mainLayout)
        self.mainLayout.addWidget(self.imageLayout,0,0,4,2)
        self.mainLayout.addLayout(self.fileSelectLayout,0,2,1,2)
        self.mainLayout.addLayout(self.windowChannelLayout,1,2,1,1)
        self.mainLayout.addLayout(self.viewControlLayout,2,2,1,1)
        self.mainLayout.addLayout(self.rangeControlLayout,3,2,1,1)
        self.mainLayout.addWidget(self.levelsPlotWidget,1,3,1,1)
        self.mainLayout.addLayout(self.levelsControlLayout,2,3,1,1)
        self.mainLayout.addWidget(self.tabs,3,3,1,1)
        self.mainWin.show()
        
    def mainWinCloseCallback(self,event):
        event.accept()
        
    def setLineColor(self):
        sender = self.mainWin.sender()
        color,ok = QtWidgets.QInputDialog.getItem(self.mainWin,'Set Line Color','Choose Color',self.plotColorOptions,editable=False)
        if not ok:
            return
        color = self.plotColors[self.plotColorOptions.index(color)]
        if sender is self.optionsMenuSetColorView3dLine:
            for windowLines in self.view3dSliceLines:
                for line in windowLines:
                    line.setPen(tuple(c*255 for c in color))
        elif sender is self.optionsMenuSetColorPoints:
            self.markPointsColor = color
            self.plotMarkedPoints(self.displayedWindows)
        elif sender is self.optionsMenuSetColorContours:
            self.contourLineColor = color
        elif sender is self.optionsMenuSetColorAtlas:
            self.atlasLineColor = color
            
    def plotImage(self):
        plt.figure(facecolor='w')
        ax = plt.subplot(1,1,1)
        img = self.getImage(atlas=False)
        if img.dtype is not np.uint8:
            img = img.astype(float)
            img /= self.levelsMax[self.selectedWindow]
        ax.imshow(img,interpolation='none')
        if len(self.selectedAtlasRegions[self.selectedWindow])>0:
            for regionID in self.selectedAtlasRegionIDs[self.selectedWindow]:
                contours = self.getAtlasRegionContours(self.selectedWindow,regionID)
                for c in contours:
                    x,y = np.squeeze(c).T
                    ax.plot(np.append(x,x[0]),np.append(y,y[0]),'-',color=self.atlasLineColor)
        x,y,rows = self.getPlotPoints(self.selectedWindow)
        if len(x)>0:
            if self.markPointsColorValues[self.selectedWindow] is None or self.markPointsColorValues[self.selectedWindow].shape[0]!=self.markedPoints[self.selectedWindow].shape[0]:
                plotStyle = 'o' if self.analysisMenuPointsLineNone.isChecked() else 'o-'
                ax.plot(x,y,plotStyle,color=self.markPointsColor,markeredgecolor=self.markPointsColor,markerfacecolor='none',markersize=self.markPointsSize)
            else:
                ax.scatter(x,y,s=self.markPointsSize,edgecolors=self.markPointsColorValuesRGB[rows],facecolors=None)
        yRange,xRange = [self.imageRange[self.selectedWindow][axis] for axis in self.imageShapeIndex[self.selectedWindow][:2]]
        ax.set_xlim([xRange[0]-0.5,xRange[1]+0.5])
        ax.set_ylim([yRange[1]+0.5,yRange[0]-0.5,])
        ax.set_xticks([])
        ax.set_yticks([])
        plt.axis('off')
        plt.tight_layout()
        plt.show()
    
    def saveImage(self):
        filePath,fileType = QtWidgets.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'Image (*.tif  *png *.jpg)')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        yRange,xRange = [self.imageRange[self.selectedWindow][axis] for axis in self.imageShapeIndex[self.selectedWindow][:2]]
        image = self.imageItem[self.selectedWindow].image.transpose((1,0,2)) if self.mainWin.sender() is self.fileMenuSaveDisplay else self.getImage()
        image = image[yRange[0]:yRange[1]+1,xRange[0]:xRange[1]+1]
        image = image[:,:,0] if self.isGray() else image[:,:,::-1]
        cv2.imwrite(filePath,image)
        
    def saveVolume(self):
        sender = self.mainWin.sender()
        if sender==self.fileMenuSaveVolumeImages:
            fileType = 'Image (*.tif  *.png *.jpg)'
        elif sender==self.fileMenuSaveVolumeMovie:
            fileType = '*.avi'
        elif sender==self.fileMenuSaveVolumeNpz:
            fileType = '*.npz'
        else:
            fileType = '*.mat'
        filePath,fileType = QtWidgets.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,fileType)
        if filePath=='':
            return
        fileType = filePath[-3:]
        self.fileSavePath = os.path.dirname(filePath)
        axis = self.imageShapeIndex[self.selectedWindow][-1]
        imageIndex = self.imageIndex[self.selectedWindow][axis]
        yRange,xRange,zRange = [self.imageRange[self.selectedWindow][ax] for ax in self.imageShapeIndex[self.selectedWindow]]
        volumeShape = tuple(r[1]-r[0]+1 for r in (yRange,xRange,zRange))
        if fileType=='avi':
            frameRate,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Set Frame Rate','Frames/s',30)
            if not ok:
                return
            vidOut = cv2.VideoWriter(filePath,-1,frameRate,volumeShape[1::-1])
        for i,imgInd in enumerate(range(zRange[0],zRange[1]+1)):
            self.imageIndex[self.selectedWindow][axis] = imgInd
            img = self.getImage()[yRange[0]:yRange[1]+1,xRange[0]:xRange[1]+1]
            if self.isGray():
                img = img[:,:,0]
            if fileType in ('tif','png','jpg'):
                if len(img.shape)>2:
                    img = img[:,:,::-1]
                cv2.imwrite(filePath[:-4]+'_'+str(i+1)+'.'+fileType,img)
            elif fileType=='avi':
                vidOut.write(img)
            else:
                if i==0:
                    dshape = volumeShape+(3,) if len(img.shape)>2 else volumeShape
                    data = np.zeros(dshape,dtype=self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].dtype)
                data[:,:,i] = img
        self.imageIndex[self.selectedWindow][axis] = imageIndex
        if fileType=='avi':
            vidOut.release()
        elif fileType in ('npz','mat'):
            if fileType=='npz':
                np.savez_compressed(filePath,imageData=data)
            else:
                scipy.io.savemat(filePath,{'imageData':data},do_compression=True)
    
    def isGray(self):            
        for fileInd in self.checkedFileIndex[self.selectedWindow]:
            imageObj = self.imageObjs[fileInd]
            channels = [ch for ch in self.selectedChannels[self.selectedWindow] if ch<imageObj.shape[3]]
            for ind,ch in enumerate(channels):
                if imageObj.rgbInd[ch]!=(0,1,2):
                    return False
        return True
                   
    def openImageFiles(self):
        filePaths,fileType = QtWidgets.QFileDialog.getOpenFileNames(self.mainWin,'Choose File(s)',self.fileOpenPath,'Image Data (*.tif *.btf *.png *.jpg *.jp2 *.npy *.npz *.nrrd *.nii)')
        if len(filePaths)>0:
            self.loadImageFiles(filePaths,fileType)
            
    def openImageSeries(self):
        filePaths,fileType = QtWidgets.QFileDialog.getOpenFileNames(self.mainWin,'Choose File(s)',self.fileOpenPath,'Image Series (*.tif *.btf *.png *.jpg *.jp2);;Bruker Dir (*.xml);;Bruker Dir + Siblings (*.xml)',self.fileSeriesType)
        if len(filePaths)>0:
            self.fileSeriesType = fileType
            self.loadImageFiles(filePaths,fileType)
        
    def loadImageFiles(self,filePaths,fileType):
        self.fileOpenPath = os.path.dirname(filePaths[0])
        if self.fileSavePath is None:
            self.fileSavePath = self.fileOpenPath
        chFileOrg = None
        numCh = None
        isMappable = any(True for f in filePaths if os.path.splitext(f)[1] in ('.tif','.btf'))
        if fileType=='Image Series (*.tif *.btf *.png *.jpg *.jp2)':
            filePaths = [filePaths]
            chFileOrg,ok = QtWidgets.QInputDialog.getItem(self.mainWin,'Import Image Series','Channel file organization:',('rgb','alternating','blocks'))
            if not ok:
                return
            if chFileOrg in ('alternating','blocks'):
                numCh,ok = QtWidgets.QInputDialog.getInt(self.mainWin,'Import Image Series','Number of channels:',1,min=1)
                if not ok:
                    return
                if len(filePaths[0])%numCh>0:
                    raise Exception('Number of files must be the same for each channel')
        elif fileType=='Bruker Dir + Siblings (*.xml)':
            dirPath = os.path.dirname(os.path.dirname(filePaths[0]))
            filePaths = []
            for item in os.listdir(dirPath):
                itemPath = os.path.join(dirPath,item)
                if os.path.isdir(itemPath):
                    for f in os.listdir(itemPath):
                        if os.path.splitext(f)[1]=='.xml':
                            fpath = os.path.join(itemPath,f)
                            if minidom.parse(fpath).getElementsByTagName('Sequence').item(0).getAttribute('type') in ('ZSeries','Single'):
                                filePaths.append(fpath)
        loadData = not self.optionsMenuImportLazy.isChecked()
        memmap = self.optionsMenuImportMemmap.isChecked() if isMappable else False
        autoColor = self.optionsMenuImportAutoColor.isChecked()
        for filePath in filePaths:
            self.loadImageData(filePath,fileType,chFileOrg,numCh,loadData,memmap,autoColor)
        
    def loadImageData(self,filePath,fileType,chFileOrg=None,numCh=None,loadData=True,memmap=False,autoColor=False):
        # filePath and fileType can also be a numpy array (Y x X x Z x Channels) and optional label, respectively
        # Provide numCh and chFileOrg if importing a multiple file image series
        self.imageObjs.append(ImageObj(filePath,fileType,chFileOrg,numCh,loadData,memmap,autoColor))
        if isinstance(filePath,np.ndarray):
            label = 'data_'+time.strftime('%Y%m%d_%H%M%S') if fileType is None else fileType
        else:
            label = filePath[0] if isinstance(filePath,list) else filePath
        self.fileListbox.addItem(label)
        if len(self.imageObjs)>1:
            self.fileListbox.item(self.fileListbox.count()-1).setCheckState(QtCore.Qt.Unchecked)
            self.stitchPos = np.concatenate((self.stitchPos,np.full((self.numWindows,1,3),np.nan)),axis=1)
        else:
            self.fileListbox.item(self.fileListbox.count()-1).setCheckState(QtCore.Qt.Checked)
            self.checkedFileIndex[self.selectedWindow] = [0]
            self.displayedWindows = [self.selectedWindow]
            self.initImageWindow()
        
    def initImageWindow(self):
        self.selectedFileIndex = [self.checkedFileIndex[self.selectedWindow][0]]
        self.fileListbox.blockSignals(True)
        self.fileListbox.setCurrentRow(self.selectedFileIndex[0])
        self.fileListbox.blockSignals(False)
        self.selectedChannels[self.selectedWindow] = [0] 
        self.imageShape[self.selectedWindow] = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].shape[:3]
        self.imageRange[self.selectedWindow] = [[0,s-1] for s in self.imageShape[self.selectedWindow]]
        self.imageIndex[self.selectedWindow] = [0,0,0]
        self.levelsMax[self.selectedWindow] = 2**self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].bitDepth-1
        self.displayImageInfo()
        self.setViewBoxRangeLimits()
        self.setViewBoxRange(self.displayedWindows)
        self.displayImage()
        self.imageViewBox[self.selectedWindow].setZValue(1)
        if self.zoomPanButton.isChecked():
            self.imageViewBox[self.selectedWindow].setMouseEnabled(x=True,y=True)
        
    def resetImageWindow(self,window=None):
        if window is None:
            window = self.selectedWindow
        self.sliceProjState[window] = 0
        self.xyzState[window] = 2
        self.imageShapeIndex[window] = (0,1,2)
        self.normState[window] = False
        self.showBinaryState[window] = False
        self.stitchState[window] = False
        self.selectedAtlasRegions[window] = []
        self.displayedWindows.remove(window)
        self.imageItem[window].setImage(np.zeros((2,2,3),dtype=np.uint8),levels=[0,255])
        self.imageViewBox[window].setMouseEnabled(x=False,y=False)
        self.imageViewBox[window].setZValue(0)
        self.clearMarkedPoints([window])
        self.alignRefWindow[window] = None
        self.localAdjustHistory[window] = []
        if window==self.selectedWindow:
            self.sliceButton.setChecked(True)
            self.zButton.setChecked(True)
            self.normDisplayCheckbox.setChecked(False)
            self.stitchCheckbox.setChecked(False)
            self.displayImageInfo()
            self.setViewBoxRange(self.displayedWindows) 
            self.resetAtlasRegionMenu()
            self.alignCheckbox.setChecked(False)
        
    def displayImageInfo(self):
        self.updateChannelList()
        self.displayImageRange()
        self.displayPixelSize()
        self.updateLevelsRange()
        self.displayImageLevels()
        
    def displayImageRange(self):
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            shape = self.imageShape[self.selectedWindow]
            self.imageDimensionsLabel.setText('XYZ Dimensions: '+str(shape[1])+', '+str(shape[0])+', '+str(shape[2]))
            for editBox,imgInd in zip(self.imageNumEditBoxes,self.imageIndex[self.selectedWindow]):
                editBox.setText(str(imgInd+1))
            for editBox,rng in zip(self.rangeEditBoxes,self.imageRange[self.selectedWindow]):
                editBox[0].setText(str(rng[0]+1))
                editBox[1].setText(str(rng[1]+1))
        else:
            self.imageDimensionsLabel.setText('XYZ Dimensions: ')
            for editBox in self.imageNumEditBoxes+tuple(box for boxes in self.rangeEditBoxes for box in boxes):
                editBox.setText('')
        
    def displayPixelSize(self):
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            pixelSize = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].pixelSize
            self.imagePixelSizeLabel.setText(u'XYZ Pixel Size (\u03BCm): '+str(pixelSize[1])+', '+str(pixelSize[0])+', '+str(pixelSize[2]))
        else:
            self.imagePixelSizeLabel.setText(u'XYZ Pixel Size (\u03BCm): ')
            
    def updateLevelsRange(self):
        self.levelsPlotItem.setXRange(0,self.levelsMax[self.selectedWindow])
        ticks = [(0,'0'),(100,'100'),(200,'200')] if self.levelsMax[self.selectedWindow]==255 else [(0,'0'),(30000,'30000'),(60000,'60000')]
        self.levelsPlotItem.getAxis('bottom').setTicks([ticks,[]])
        lowRange = (0,self.levelsMax[self.selectedWindow]-1)
        highRange = (1,self.levelsMax[self.selectedWindow])
        self.lowLevelLine.setBounds(lowRange)
        self.highLevelLine.setBounds(highRange)
        self.lowLevelBox.setRange(lowRange[0],lowRange[1])
        self.highLevelBox.setRange(highRange[0],highRange[1])
            
    def displayImageLevels(self):
        for box in self.levelsBoxes:
            box.blockSignals(True)
        fileInd = set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex)
        if len(fileInd)>0:
            isSet = False
            if self.showVolumeLevelsButton.isChecked():
                pixIntensityHist = np.zeros(self.levelsMax[self.selectedWindow]+1)
            for i in fileInd:
                channels = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannels[self.selectedWindow]
                channels = [ch for ch in channels if ch<self.imageObjs[i].shape[3]]
                if len(channels)>0:
                    if self.showVolumeLevelsButton.isChecked():
                        pixIntensityHist += np.histogram(self.imageObjs[i].getData(channels),np.arange(self.levelsMax[self.selectedWindow]+2))[0]
                    if not isSet:
                        levels = self.imageObjs[i].levels[channels[0]]
                        self.lowLevelLine.setValue(levels[0])
                        self.highLevelLine.setValue(levels[1])
                        self.lowLevelBox.setValue(levels[0])
                        self.highLevelBox.setValue(levels[1])
                        self.gammaBox.setValue(self.imageObjs[i].gamma[channels[0]])
                        self.alphaBox.setValue(self.imageObjs[i].alpha)
                        isSet = True
            if self.showVolumeLevelsButton.isChecked():
                self.updateLevelsPlot(pixIntensityHist)
        else:
            self.lowLevelLine.setValue(0)
            self.highLevelLine.setValue(self.levelsMax[self.selectedWindow])
            self.lowLevelBox.setValue(0)
            self.highLevelBox.setValue(self.levelsMax[self.selectedWindow])
            self.gammaBox.setValue(1)
            self.alphaBox.setValue(1)
            self.updateLevelsPlot()
        for box in self.levelsBoxes:
            box.blockSignals(False)             
                
    def updateLevelsPlot(self,pixIntensityHist=None):
        if pixIntensityHist is None:
            self.levelsPlot.setData(x=[],y=[])
            self.levelsPlotItem.setYRange(0,1)
            self.levelsPlotItem.getAxis('left').setTicks([[(0,'0'),(1,'1')],[]])
        else:
            pixIntensityHist[pixIntensityHist<1] = 1
            pixIntensityHist = np.log10(pixIntensityHist)
            self.levelsPlot.setData(pixIntensityHist)
            histMax = pixIntensityHist.max()
            self.levelsPlotItem.setYRange(0,round(histMax))
            self.levelsPlotItem.getAxis('left').setTicks([[(0,'0'),(int(histMax),'1e'+str(int(histMax)))],[]])
            
    def convertImage(self):
        self.checkIfSelectedDisplayedBeforeDtypeOrShapeChange()
        dtype = np.uint8 if self.mainWin.sender() is self.imageMenuConvertTo8Bit else np.uint16
        for fileInd in self.selectedFileIndex:
            if self.imageObjs[fileInd].dtype!=dtype:
                self.imageObjs[fileInd].convertDataType()
        for window in self.getAffectedWindows():
            self.levelsMax[window] = 2**self.imageObjs[self.checkedFileIndex[window][0]].bitDepth-1
            if window==self.selectedWindow:
                self.updateLevelsRange()
                self.displayImageLevels()
                self.displayImage()
                
    def invertImage(self):
        for fileInd in self.selectedFileIndex:
            self.imageObjs[fileInd].invert()
        if self.selectedWindow in self.getAffectedWindows():
            self.displayImageLevels()
            self.displayImage()
            
    def normalizeImage(self):
        option = 'images' if self.mainWin.sender() is self.imageMenuNormImages else 'volume'
        for fileInd in self.selectedFileIndex:
            self.imageObjs[fileInd].normalize(option)
        if self.selectedWindow in self.getAffectedWindows():
            self.displayImageLevels()
            self.displayImage()
            
    def changeBackground(self):
        thresh,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Set Threshold','fraction above/below min/max:',0,min=0,max=1,decimals=3)
        if not ok:
            return
        option = 'b2w' if self.mainWin.sender() is self.imageMenuBackgroundBtoW else 'w2b'
        for fileInd in self.selectedFileIndex:
            self.imageObjs[fileInd].changeBackground(option,thresh)
        if self.selectedWindow in self.getAffectedWindows():
            self.displayImageLevels()
            self.displayImage()
            
    def setPixelSize(self):
        if self.mainWin.sender() is self.imageMenuPixelSizeXY:
            dim = 'XY'
            ind = (0,1)
        else:
            dim = 'Z'
            ind = (2,)
        val,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Set '+dim+' Pixel Size','\u03BCm/pixel:',0,min=0,decimals=4)
        if ok and val>0:
            for fileInd in self.selectedFileIndex:
                for i in ind:
                    self.imageObjs[fileInd].pixelSize[i] = val
            self.displayPixelSize()
            
    def resampleImage(self):
        sender = self.mainWin.sender()
        if sender==self.imageMenuResamplePixelSize:
            if any(self.imageObjs[fileInd].pixelSize[0] is None for fileInd in self.selectedFileIndex):
                raise Exception('Must define pixel size before using new pixel size for resampling')
            newPixelSize,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Resample Pixel Size','\u03BCm/pixel:',0,min=0,decimals=4)
            if not ok or newPixelSize==0:
                return
        else:
            scaleFactor,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Resample Scale Factor','scale factor (new/old size):',1,min=0.001,decimals=4)
            if not ok or scaleFactor==1:
                return
        self.checkIfSelectedDisplayedBeforeDtypeOrShapeChange()            
        for fileInd in self.selectedFileIndex:
            oldPixelSize = self.imageObjs[fileInd].pixelSize[0]
            if sender==self.imageMenuResamplePixelSize:
                scaleFactor = oldPixelSize/newPixelSize
            else:
                newPixelSize = None if oldPixelSize is None else round(oldPixelSize/scaleFactor,4)
            if newPixelSize is not None:
                self.imageObjs[fileInd].pixelSize[:2] = [newPixelSize]*2
            shape = tuple(int(round(self.imageObjs[fileInd].shape[i]*scaleFactor)) for i in (0,1))+self.imageObjs[fileInd].shape[2:]
            scaledData = np.zeros(shape,dtype=self.imageObjs[fileInd].dtype)
            interpMethod = cv2.INTER_AREA if scaleFactor<1 else cv2.INTER_LINEAR
            dataIter = self.imageObjs[fileInd].getDataIterator()
            for i in range(shape[2]):
                for ch in range(shape[3]):
                    scaledData[:,:,i,ch] = cv2.resize(next(dataIter),shape[1::-1],interpolation=interpMethod)
            self.imageObjs[fileInd].data = scaledData
            self.imageObjs[fileInd].shape = shape
        windows = self.getAffectedWindows()
        for window in windows:
            self.imageShape[window] = self.imageObjs[self.checkedFileIndex[window][0]].shape[:3]
            self.setImageRange(window=window)
            if window==self.selectedWindow:
                self.displayImageInfo()
        self.setViewBoxRangeLimits(windows)
        self.displayImage(windows)
        
    def flipImage(self):
        sender = self.mainWin.sender()
        if sender in (self.imageMenuFlipImgHorz,self.imageMenuFlipImgVert):
            fileInd = set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex)
            if sender is self.imageMenuFlipImgVert:
                axis = self.imageShapeIndex[self.selectedWindow][0]
            else:
                axis = self.imageShapeIndex[self.selectedWindow][1]
            imgAxis = self.imageShapeIndex[self.selectedWindow][2]
            imgInd = self.imageIndex[self.selectedWindow][imgAxis]
        else:
            fileInd = self.selectedFileIndex
            if sender is self.imageMenuFlipVolX:
                axis = 1
            elif sender is self.imageMenuFlipVolY:
                axis = 0
            else:
                axis = 2
            imgAxis = imgInd = None
        for f in fileInd:
            self.imageObjs[f].flip(axis,imgAxis,imgInd)
        self.displayImage(self.getAffectedWindows())
        
    def rotateImage(self):
        self.checkIfSelectedDisplayedBeforeDtypeOrShapeChange()
        sender = self.mainWin.sender()
        axes = self.imageShapeIndex[self.selectedWindow]
        if sender in (self.imageMenuRotate90C,self.imageMenuRotate90CC):
            direction = -1 if sender is self.imageMenuRotate90C else 1
            for fileInd in self.selectedFileIndex:
                self.imageObjs[fileInd].rotate90(direction,axes[:2])
        else:
            pts = self.markedPoints[self.selectedWindow]
            if sender is self.imageMenuRotateAngle:
                angle,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Rotation Angle','degrees:',0,decimals=2)
                if not ok or angle==0:
                    return
                self.rotationAngle = [angle]
                self.rotationAxes = [axes[:2]]
            else:
                if pts is None or pts.shape[0]<2:
                    raise Exception('At least two marked points are required for rotation to line')
                y,x,z = pts[:,axes].T
                xangle = math.atan(1/np.polyfit(x,y,1)[0]) if any(np.diff(x)) else 0
                zangle = math.atan(1/np.polyfit(z,y,1)[0]) if any(np.diff(z)) else 0
                self.rotationAngle = [math.degrees(xangle),math.degrees(zangle)]
                self.rotationAxes = [axes[:2],[axes[0],axes[2]]]
                # only use portion of image volume containing points
                pointsLength = ((z.max()-z.min())**2+(y.max()-y.min())**2)**0.5
                pad = int(pointsLength*math.tan(zangle))
                smax = max(self.imageObjs[fileInd].shape[axes[2]] for fileInd in self.selectedFileIndex)
                pad = (min(z.min(),-pad+5),5) if pad<0 else (5,min(smax-z.max(),pad+5))
                for fileInd in self.selectedFileIndex:
                    self.imageObjs[fileInd].data = self.imageObjs[fileInd].data[:,:,int(z.min()-pad[0]):int(math.ceil(z.max())+pad[1]+1)]
                    self.imageObjs[fileInd].shape = self.imageObjs[fileInd].data.shape
                self.markedPoints[self.selectedWindow][:,2] -= z.min()-pad[0]
            for i,(angle,ax) in enumerate(zip(self.rotationAngle,self.rotationAxes)):
                if angle!=0:
                    if 0 in ax:
                        angle *= -1
                        self.rotationAngle[i] *= -1
                    s = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].shape[:3]
                    center = [(s[i]-1)/2 for i in ax]
                    for fileInd in self.selectedFileIndex:
                        self.imageObjs[fileInd].rotate(angle,ax)
                    if pts is not None:
                        # translate points such that origin is center of rotation , rotate, then translate back to image origin
                        # ynew = -x*sin(a) + y*cos(a)
                        # xnew = x*cos(a) + y*sin(a)
                        a = math.radians(angle)
                        if 0 not in ax:
                            a *= -1
                        p = pts[:,ax]-center
                        s = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].shape[:3]
                        c = [(s[i]-1)/2 for i in ax]
                        pts[:,ax[0]] = -p[:,1]*math.sin(a)+p[:,0]*math.cos(a)+c[0]
                        pts[:,ax[1]] = np.mean(p[:,1]*math.cos(a)+p[:,0]*math.sin(a)+c[1])
                        imgInd = int(round(pts[0,ax[1]]))
                        self.imageIndex[self.selectedWindow][ax[1]] = imgInd
                        self.imageNumEditBoxes[ax[1]].setText(str(imgInd+1))
            if len(self.selectedAtlasRegions[self.selectedWindow])>0:
                self.rotateAnnotationData()
            if pts is not None:
                self.fillPointsTable()
        affectedWindows = self.getAffectedWindows()
        if self.stitchCheckbox.isChecked():
            for window in affectedWindows:
                self.holdStitchRange = False
            self.updateStitchShape(affectedWindows)
        else:
            for window in affectedWindows:
                self.imageShape[window] = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].shape[:3]
            self.setImageRange()
            self.displayImageRange()
            self.setViewBoxRangeLimits(affectedWindows)
            self.setViewBoxRange(affectedWindows)
        self.displayImage(affectedWindows)
        
    def saveOffsets(self):
        if len(self.selectedFileIndex)>1:
            raise Exception('Select a single image object to return its offsets')
        filePath,fileType = QtWidgets.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.npy')
        if filePath=='':
            return
        offset = self.imageObjs[self.selectedFileIndex[0]].getOffsets()
        np.save(filePath,offset)
        
    def clearLocalAdjustHistory(self):
        self.localAdjustHistory = [[] for _ in range(self.numWindows)]
    
    def saveLocalAdjustHistory(self):
        filePath,fileType = QtWidgets.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.npz')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        np.savez(filePath,*self.localAdjustHistory[self.selectedWindow])
    
    def loadLocalAdjust(self):
        filePath,fileType = QtWidgets.QFileDialog.getOpenFileName(self.mainWin,'Choose File',self.fileOpenPath,'*.npz')
        if filePath=='':
            return
        self.fileOpenPath = os.path.dirname(filePath)
        f = np.load(filePath)
        localAdjustHistory = [f[key] for key in f.keys()]
        currentPixelSize = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].pixelSize[0]
        if currentPixelSize is None:
            currentPixelSize,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Set Current XY Pixel Size','\u03BCm/pixel:',0,min=0,decimals=4)
            if not ok or currentPixelSize==0:
                return
            for fileInd in self.checkedFileIndex[self.selectedWindow]:
                self.imageObjs[fileInd].pixelSize[:2] = [currentPixelSize]*2
            self.displayPixelSize()        
        newPixelSize,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Set New XY Pixel Size','\u03BCm/pixel:',currentPixelSize,min=0,decimals=4)
        if not ok or newPixelSize==0:
            return
        scaleFactor = currentPixelSize/newPixelSize
        numImgs = self.imageShape[self.selectedWindow][2]
        mask = [[] for _ in range(numImgs)]
        warpMat = [[] for _ in range(numImgs)]
        for i in range(numImgs):
                for pts in localAdjustHistory:
                    if pts[0,0,2]==i:
                        m = np.zeros((2,)+self.imageShape[self.selectedWindow][:2],dtype=np.uint8)
                        mpts = [(p[None,:,1::-1]/scaleFactor).astype(int) for p in pts]
                        cv2.fillPoly(m[0],[mpts[0]],255)
                        cv2.fillPoly(m[1],[mpts[1]],255)
                        mask[i].append(m.astype(bool))
                        warpMat[i].append(cv2.estimateRigidTransform(mpts[0],mpts[1],fullAffine=False))
        for fileInd in self.checkedFileIndex[self.selectedWindow]:
            shape = tuple(int(round(self.imageObjs[fileInd].shape[i]*scaleFactor)) for i in (0,1))+self.imageObjs[fileInd].shape[2:]
            adjustedData = np.zeros(shape,dtype=self.imageObjs[fileInd].dtype)
            interpMethod = cv2.INTER_AREA if scaleFactor<1 else cv2.INTER_LINEAR
            dataIter = self.imageObjs[fileInd].getDataIterator()
            for i in range(shape[2]):
                for ch in range(shape[3]):
                    data = next(dataIter)
                    for m,w in zip(mask[i],warpMat[i]):
                        warpData = cv2.warpAffine(data,w,data.shape[1::-1],flags=cv2.INTER_LINEAR)
                        data[m[0]] = 0
                        data[m[1]] = warpData[m[1]]
                    adjustedData[:,:,i,ch] = data if scaleFactor==1 else cv2.resize(data,shape[1::-1],interpolation=interpMethod)
            self.imageObjs[fileInd].data = adjustedData
            self.imageObjs[fileInd].shape = shape
        if scaleFactor!=1:
            self.imageShape[self.selectedWindow] = shape[:3]
            self.setImageRange()
            self.displayImageInfo()
        self.setViewBoxRangeLimits()
        self.displayImage()
    
    def transformImage(self):
        sender = self.mainWin.sender()
        self.checkIfSelectedDisplayedBeforeDtypeOrShapeChange()
        axis = self.imageShapeIndex[self.selectedWindow][2]
        rng = self.imageRange[self.selectedWindow][axis]
        if sender is self.imageMenuTransformAligned:
            refWin = self.alignRefWindow[self.selectedWindow]
            if refWin is None:
                raise Exception('Image must be aligned to reference before transforming')
            sliceProjState = []
            imageIndex = []
            for window in (refWin,self.selectedWindow):
                sliceProjState.append(self.sliceProjState[window])
                imageIndex.append(self.imageIndex[window][axis])
                self.sliceProjState[window] = 0
            self.transformShape = tuple(self.imageShape[refWin][i] for i in self.imageShapeIndex[refWin][:2])+(rng[1]-rng[0]+1,)
            self.transformMatrix = np.zeros((rng[1]-rng[0]+1,2,3),dtype=np.float32)
        else:
            filePath,fileType = QtWidgets.QFileDialog.getOpenFileName(self.mainWin,'Choose File',self.fileOpenPath,'*.npz')
            if filePath=='':
                return
            self.fileOpenPath = os.path.dirname(filePath)
            transformData = np.load(filePath)
            self.transformShape = tuple(transformData['transformShape'])
            self.transformMatrix = transformData['transformMatrix']
        for fileInd in self.checkedFileIndex[self.selectedWindow]:
            dataIter = self.imageObjs[fileInd].getDataIterator(rangeSlice=slice(rng[0],rng[1]+1))
            warpData = np.zeros(self.transformShape+(self.imageObjs[fileInd].shape[3],),dtype=self.imageObjs[fileInd].dtype)
            for ind,imgInd in enumerate(range(rng[0],rng[1]+1)):
                if sender is self.imageMenuTransformAligned:
                    mask = []
                    for window in (refWin,self.selectedWindow):
                        if window==refWin:
                            self.imageIndex[window][axis] = self.getAlignedRefImageIndex(self.selectedWindow,imgInd)
                        else:
                            self.imageIndex[window][axis] = imgInd
                        image = self.getImage(window,binary=True).max(axis=2)
                        contours,_ = cv2.findContours(image,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                        mask.append(np.zeros(image.shape,dtype=np.uint8))
                        cv2.drawContours(mask[-1],contours,-1,1,-1)
                    criteria = (cv2.TERM_CRITERIA_COUNT+cv2.TERM_CRITERIA_EPS,1000,1e-4)
                    _,self.transformMatrix[ind] = cv2.findTransformECC(mask[1],mask[0],np.eye(2,3,dtype=np.float32),cv2.MOTION_AFFINE,criteria,inputMask=None,gaussFiltSize=1)
                for ch in range(warpData.shape[3]):
                    warpData[:,:,ind,ch] = cv2.warpAffine(next(dataIter),self.transformMatrix[ind],self.transformShape[1::-1],flags=cv2.INTER_LINEAR)
            self.imageObjs[fileInd].data = warpData
            self.imageObjs[fileInd].shape = warpData.shape
        if sender is self.imageMenuTransformAligned:
            for ind,window in enumerate((refWin,self.selectedWindow)):
                self.sliceProjState[window] = sliceProjState[ind]
                self.imageIndex[window][axis] = imageIndex[ind]
            self.imageIndex[self.selectedWindow][axis] -= rng[0]
            self.alignIndex[self.selectedWindow][self.alignIndex[self.selectedWindow]>=0] -= rng[0]
        self.imageShape[self.selectedWindow] = self.transformShape
        self.setImageRange()
        self.setViewBoxRangeLimits()
        self.displayImageInfo()
        self.displayImage()
        
    def saveTransformMatrix(self):
        filePath,fileType = QtWidgets.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.npz')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        np.savez(filePath,transformShape=np.array(self.transformShape),transformMatrix=self.transformMatrix)
        
    def warpImage(self):
        refWin = self.alignRefWindow[self.selectedWindow]
        if refWin is None:
            raise Exception('Image must be aligned to reference before warping')
        refPoints = self.markedPoints[refWin]
        warpPoints = self.markedPoints[self.selectedWindow]
        shapeIndex = self.imageShapeIndex[refWin]
        axis = shapeIndex[2]
        rng = self.imageRange[self.selectedWindow][axis]
        h,w = (self.imageShape[refWin][i] for i in shapeIndex[:2])
        boundaryPts = getDelauneyBoundaryPoints(w,h)
        for fileInd in self.checkedFileIndex[self.selectedWindow]:
            imageData = self.imageObjs[fileInd].data[:,:,rng[0]:rng[1]+1].copy()
            for ind,imgInd in enumerate(range(rng[0],rng[1]+1)):
                # append boundaryPts to (x,y) float32 point arrays
                refInd = self.getAlignedRefImageIndex(self.selectedWindow,imgInd)
                if refInd in refPoints[:,axis] and imgInd in warpPoints[:,axis]:
                    refPts,warpPts = (np.concatenate((pts[pts[:,axis]==i][:,shapeIndex[1::-1]],boundaryPts),axis=0).astype(np.float32) for pts,i in zip((refPoints,warpPoints),(refInd,imgInd)))
                    # get Delaunay triangles as indices of refPts (point1Index,point2Index,point3Index)
                    triangles = getDelauneyTriangles(refPts,w,h)
                    triPtInd = np.zeros((triangles.shape[0],3),dtype=int)
                    for i,tri in enumerate(triangles):
                        for j in (0,2,4):
                            triPtInd[i,j//2] = np.where(np.all(refPts==tri[j:j+2],axis=1))[0][0]
                    # warp each triangle
                    for tri in triPtInd:
                        refTri = refPts[tri]
                        warpTri = warpPts[tri]
                        refRect = cv2.boundingRect(refTri)
                        warpRect = cv2.boundingRect(warpTri)
                        refTri -= refRect[:2]
                        warpTri -= warpRect[:2]
                        refSlice,warpSlice = ((slice(r[1],r[1]+r[3]),slice(r[0],r[0]+r[2])) for r in (refRect,warpRect))
                        mask = np.zeros(refRect[:-3:-1],dtype=np.uint8)
                        cv2.fillConvexPoly(mask,refTri.astype(int),1)
                        mask = mask.astype(bool)
                        warpMatrix = cv2.getAffineTransform(warpTri,refTri)
                        for ch in range(imageData.shape[3]):
                            warpData = cv2.warpAffine(imageData[warpSlice[0],warpSlice[1],ind,ch],warpMatrix,refRect[2:],flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
                            self.imageObjs[fileInd].data[refSlice[0],refSlice[1],imgInd,ch][mask] = warpData[mask]
        self.displayImage()
    
    def makeCCFVolume(self):
        self.checkIfSelectedDisplayedBeforeDtypeOrShapeChange()
        refWin = self.alignRefWindow[self.selectedWindow]
        if refWin is None or self.imageObjs[self.checkedFileIndex[refWin][0]].fileType!='nrrd' or self.imageShapeIndex[self.selectedWindow][2]!=2:
            raise Exception('Image must be aligned to Allen Atlas coronal sections')
        rng = self.imageRange[self.selectedWindow][2]
        refShape = self.imageObjs[self.checkedFileIndex[refWin][0]].shape[:3]
        for fileInd in self.checkedFileIndex[self.selectedWindow]:
            data = self.imageObjs[fileInd].data[:,:,rng[0]:rng[1]+1]
            ccfData = np.zeros(refShape+(data.shape[3],),dtype=data.dtype)
            if self.mainWin.sender() is self.imageMenuMakeCCFIntp:
                x = np.arange(data.shape[2])
                intp = scipy.interpolate.interp1d(x,data,axis=2)
                alignInd = self.alignIndex[self.selectedWindow]>=0
                ccfData[:,:,alignInd] = intp(np.linspace(x[0],x[-1],np.count_nonzero(alignInd)))
            else:
                for i in range(rng[0],rng[1]+1):
                    for ind in np.where(self.alignIndex[self.selectedWindow]==i)[0]:
                        ccfData[:,:,ind] = data[:,:,i]
            self.imageObjs[fileInd].data = ccfData
            self.imageObjs[fileInd].shape = ccfData.shape
        self.imageIndex[self.selectedWindow][2] = np.where(self.alignIndex[self.selectedWindow]==rng[0])[0][0]
        self.alignRefWindow[self.selectedWindow] = None
        self.alignCheckbox.setChecked(False)
        self.imageShape[self.selectedWindow] = refShape
        self.setImageRange()
        self.setViewBoxRangeLimits()
        self.displayImageInfo()
        self.displayImage()
        
    def checkIfSelectedDisplayedBeforeDtypeOrShapeChange(self):
        for window in self.displayedWindows:
            selected = [True if i in self.selectedFileIndex else False for i in self.checkedFileIndex[window]]
            if (self.linkWindowsCheckbox.isChecked() or any(selected)) and not all(selected):
                raise Exception('Must select all images displayed in the same window or in linked windows before data type or shape change')
            
    def setViewBoxRangeLimits(self,windows=None):
        if windows is None:
            windows = [self.selectedWindow]
        self.ignoreImageRangeChange = True
        for window in windows:
            ymax,xmax = [math.ceil(self.imageShape[window][i]/self.displayDownsample[window])-1 for i in self.imageShapeIndex[window][:2]]
            self.imageViewBox[window].setLimits(xMin=0,xMax=xmax,yMin=0,yMax=ymax,minXRange=3,maxXRange=xmax,minYRange=3,maxYRange=ymax)
        self.ignoreImageRangeChange = False
        
    def setViewBoxRange(self,windows=None):
        # square viewBox rectangle to fill layout (or subregion if displaying mulitple image windows)
        # adjust aspect to match image range
        if windows is None:
            windows = [self.selectedWindow]
        layoutRect = self.imageLayout.viewRect()
        left = layoutRect.left()
        top = layoutRect.top()
        width = layoutRect.width()
        height = layoutRect.height()
        if width>height:
            left += (width-height)/2
            width = height
        else:
            top += (height-width)/2
        self.ignoreImageRangeChange = True
        numDisplayedWindows = len(self.displayedWindows)
        for window in windows:
            x,y,size = left,top,width
            if numDisplayedWindows>1:
                size /= 2
                position = self.displayedWindows.index(window)
                if numDisplayedWindows<3:
                    x += size/2   
                elif position in (2,3):
                    x += size
                if position in (1,3):
                    y += size
            offset = 0.01*size
            x += offset
            y += offset
            size -= 2*offset
            yRange,xRange,zRange = [[r//self.displayDownsample[window] for r in self.imageRange[window][axis]] for axis in self.imageShapeIndex[window]]
            yExtent,xExtent,zExtent = [r[1]-r[0] for r in (yRange,xRange,zRange)]
            if self.view3dCheckbox.isChecked():
                maxXYExtent = max(yExtent,xExtent)
                if maxXYExtent<zExtent:
                    offset = (size-size*maxXYExtent/zExtent)/2
                    x += offset
                    y += offset
                    size *= maxXYExtent/zExtent
            aspect = xExtent/yExtent
            if (numDisplayedWindows!=2 and aspect>1) or (numDisplayedWindows==2 and aspect>2):
                w = size
                h = w/aspect
                y += (w-h)/2
            else:
                h = size
                w = h*aspect
                x += (h-w)/2
            x,y,w,h = (int(round(n)) for n in (x,y,w,h))
            self.imageViewBox[window].setGeometry(x,y,w,h)
            self.imageViewBox[window].setRange(xRange=xRange,yRange=yRange,padding=0)
        self.ignoreImageRangeChange = False
        
    def imageLayoutResizeCallback(self,event):
        self.imageLayoutResizeFcn(event)
        if len(self.displayedWindows)>0:
            self.setViewBoxRange(self.displayedWindows)
        
    def downsampleEditCallback(self):
        val = int(float(self.downsampleEdit.text()))
        if val<1:
            val = 1
        if val==self.displayDownsample[self.selectedWindow]:
            return
        self.displayDownsample[self.selectedWindow] = val
        if self.selectedWindow in self.displayedWindows:
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            for window in windows:
                self.displayDownsample[window] = val
                self.setViewBoxRangeLimits(windows)
                self.setViewBoxRange(windows)
                self.displayImage(windows)
        
    def displayImage(self,windows=None):
        if windows is None:
            windows = [self.selectedWindow]
        for window in windows:
            image = self.getImage(window,downsample=self.displayDownsample[window])
            levels = [0,255] if image.dtype==np.uint8 else [0,self.levelsMax[window]]
            self.imageItem[window].setImage(image.transpose((1,0,2)),levels=levels)
            if self.showImageLevelsButton.isChecked() and window is self.selectedWindow:
                self.updateLevelsPlot(np.histogram(image,np.arange(self.levelsMax[window]+2))[0])
        self.plotMarkedPoints(windows)
        
    def getImage(self,window=None,downsample=1,binary=False,atlas=True):
        if window is None:
            window = self.selectedWindow
        if self.showBinaryState[window]:
            binary = True
        imageShape = [int(math.ceil(self.imageShape[window][i]/downsample)) for i in self.imageShapeIndex[window][:2]]
        image = np.zeros((imageShape[0],imageShape[1],3))
        for fileInd in self.checkedFileIndex[window]:
            imageObj = self.imageObjs[fileInd]
            if self.stitchState[window]:
                i,j = (slice(int(self.stitchPos[window,fileInd,i]//downsample),int(self.stitchPos[window,fileInd,i]+math.ceil(imageObj.shape[i])/downsample)) for i in self.imageShapeIndex[window][:2])
            else:
                i,j = (slice(0,int(math.ceil(imageObj.shape[i]/downsample))) for i in self.imageShapeIndex[window][:2])
            channels = [ch for ch in self.selectedChannels[window] if ch<imageObj.shape[3]]
            data,alphaMap = self.getImageData(imageObj,fileInd,window,channels,downsample,binary)
            if data is not None:
                if not self.stitchState[window]:
                    if alphaMap is not None:
                        image *= 1-alphaMap
                    if imageObj.alpha<1:
                        image *= 1-imageObj.alpha
                for ind,ch in enumerate(channels):
                    for k in imageObj.rgbInd[ch]:
                        if self.stitchState[window] and self.imageMenuStitchOverlayMax.isChecked():
                            image[i,j,k] = np.maximum(image[i,j,k],data[:,:,ind],out=image[i,j,k])
                        elif imageObj.alpha<1 or alphaMap is not None:
                            image[i,j,k] += data[:,:,ind]
                        else:
                            image[i,j,k] = data[:,:,ind]
        if self.normState[window]:
            levels = (image.min(),image.max())
            image.clip(levels[0],levels[1],out=image)
            image -= levels[0] 
            image /= (levels[1]-levels[0])/self.levelsMax[window]
        dtype = np.uint8 if self.levelsMax[window]==255 or binary else np.uint16
        image = image.astype(dtype)
        if atlas and len(self.selectedAtlasRegions[window])>0:
            color = tuple(self.levelsMax[window]*c for c in self.atlasLineColor)
            for regionID in self.selectedAtlasRegionIDs[window]:
                contours = self.getAtlasRegionContours(window,regionID,downsample)
                cv2.drawContours(image,contours,-1,color,1,cv2.LINE_AA)
        return image
                    
    def getImageData(self,imageObj,fileInd,window,channels,downsample,binary):
        isProj = self.sliceProjState[window]
        axis = self.imageShapeIndex[window][2]
        if isProj:
            rng = (0,imageObj.shape[axis]-1) if self.stitchState[window] else self.imageRange[window][axis]
            rangeSlice = slice(rng[0],rng[1]+1)
        else:
            i = self.imageIndex[window][axis]
            if i<0:
                return None,None
            if self.stitchState[window]:
                i -= int(self.stitchPos[window,fileInd,axis])
                if not 0<=i<imageObj.shape[axis]:
                    return None,None
            rangeSlice = slice(i,i+1)
        if imageObj.data is None:
            data = np.zeros([imageObj.shape[i] for i in self.imageShapeIndex[window][:2]]+[len(channels)],dtype=imageObj.dtype)
            zSlice = rangeSlice if axis==2 else slice(0,imageObj.shape[2])
            dataIter = imageObj.getDataIterator(channels,zSlice)
            for i in range(zSlice.start,zSlice.stop):
                for chInd,_ in enumerate(channels):
                    d = next(dataIter)
                    if axis==2:
                        chData = data[:,:,chInd]
                    elif axis==1:
                        chData = data[:,i,chInd]
                        d = d[:,rangeSlice].max(axis=1)
                    else:
                        chData = data[i,:,chInd]
                        d = d[rangeSlice,:].max(axis=0)
                    chData = np.maximum(d,chData,out=chData)
        else:
            if axis==2:
                data = imageObj.data[:,:,rangeSlice,channels]
            elif axis==1:
                data = imageObj.data[:,rangeSlice,:,channels]
            else:
                data = imageObj.data[rangeSlice,:,:,channels].transpose((0,2,1,3))
            data = data.max(axis)
        data = data[::downsample,::downsample].astype(float)
        for chInd,ch in enumerate(channels):
            chData = data[:,:,chInd]
            if binary:
                aboveThresh = chData>=imageObj.levels[ch][1]
                chData[aboveThresh] = 255
                chData[~aboveThresh] = 0
            else:
                levels = imageObj.levels[ch]
                if levels[0]>0 or levels[1]<self.levelsMax[window]:
                    chData.clip(levels[0],levels[1],out=chData)
                    chData -= imageObj.levels[ch][0] 
                    chData /= (levels[1]-levels[0])/self.levelsMax[window]
                if imageObj.gamma[ch]!=1:
                    chData /= self.levelsMax[window]
                    chData **= imageObj.gamma[ch]
                    chData *= self.levelsMax[window]
        if imageObj.alphaMap is None:
            alphaMap = None
        else:
            if axis==2:
                alphaMap = imageObj.alphaMap[:,:,rangeSlice]
            elif axis==1:
                alphaMap = imageObj.alphaMap[:,rangeSlice,:]
            else:
                alphaMap = imageObj.alphaMap[rangeSlice,:,:].transpose((0,2,1))
            alphaMap = (alphaMap.max(axis).astype(float)/self.levelsMax[window])[:,:,None]
            data *= alphaMap
        if imageObj.alpha<1:
            data *= imageObj.alpha
        return data,alphaMap
        
    def getAtlasRegionContours(self,window,regionID,downsample=1):
        isProj = self.sliceProjState[window]
        axis = self.imageShapeIndex[window][2]
        if isProj:
            rng = self.imageRange[window][axis]
            if self.alignRefWindow[window] is not None:
                rng = [self.getAlignedRefImageIndex(window,i) for i in rng]
            ind = slice(rng[0],rng[1]+1)
        else:
            ind = self.imageIndex[window][axis]
            if self.alignRefWindow[window] is not None:
                ind = self.getAlignedRefImageIndex(window,ind)
        if axis==2:
            a = self.atlasAnnotationData[:,:,ind]
        elif axis==1:
            a = self.atlasAnnotationData[:,ind,:]
        else:
            a = self.atlasAnnotationData.transpose((0,2,1))[ind,:,:]
        mask = np.in1d(a,regionID).reshape(a.shape)
        if isProj:
            mask = mask.max(axis=axis)
        mask = mask[::downsample,::downsample]
        if self.atlasMenuHemiLeft.isChecked():
            mask[:,mask.shape[1]//2:] = 0
        elif self.atlasMenuHemiRight.isChecked():
            mask[:,:mask.shape[1]//2] = 0
        contours,_ = cv2.findContours(mask.copy(order='C').astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        return contours
        
    def loadAtlasTemplate(self):
        if self.atlasTemplate is None:
            n = len(self.imageObjs)
            self.openImageFiles()
            if len(self.imageObjs)>n:
                self.atlasTemplate = self.imageObjs[-1].data
        else:
            self.loadImageData(self.atlasTemplate,'Atlas Template')
            self.imageObjs[-1].pixelSize = [25.0]*3
        
    def setAtlasRegions(self):
        if self.atlasAnnotationData is None:
            filePath,fileType = QtWidgets.QFileDialog.getOpenFileName(self.mainWin,'Choose Annotation Data File',self.fileOpenPath,'*.nrrd')
            if filePath=='':
                self.resetAtlasRegionMenu()
                return
            self.fileOpenPath = os.path.dirname(filePath)
            self.atlasAnnotationData,_ = nrrd.read(filePath)
            self.atlasAnnotationData = self.atlasAnnotationData.transpose((1,2,0))
        if self.atlasAnnotationRegions is None:
            filePath,fileType = QtWidgets.QFileDialog.getOpenFileName(self.mainWin,'Choose Annotation Region Hierarchy File',self.fileOpenPath,'*.xml')
            if filePath=='':
                self.resetAtlasRegionMenu()
                return
            self.fileOpenPath = os.path.dirname(filePath)
            self.atlasAnnotationRegions = minidom.parse(filePath)
        selectedRegions = [ind for ind,region in enumerate(self.atlasRegionMenu) if region.isChecked()]
        regionIDs = [self.getAtlasRegionID(self.atlasRegionLabels[ind]) for ind in selectedRegions]
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.selectedAtlasRegions[window] = selectedRegions
            self.selectedAtlasRegionIDs[window] = regionIDs
        self.displayImage(windows)
        
    def getAtlasRegionID(self,regionLabel):
        for structure in self.atlasAnnotationRegions.getElementsByTagName('structure'):
            if structure.childNodes[7].childNodes[0].nodeValue[1:-1]==regionLabel:
                return [int(sub.childNodes[0].nodeValue) for sub in structure.getElementsByTagName('id')]
        return []
        
    def resetAtlasRegionMenu(self):
        for region in self.atlasRegionMenu:
            if region.isChecked():
                region.setChecked(False)
        
    def clearAtlasRegions(self):
        if len(self.selectedAtlasRegions[self.selectedWindow])>0:
            self.resetAtlasRegionMenu()
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            for window in windows:
                self.selectedAtlasRegions[window] = []
            self.displayImage(windows)
            
    def setAtlasHemi(self):
        sender = self.mainWin.sender()
        for option in (self.atlasMenuHemiBoth,self.atlasMenuHemiLeft,self.atlasMenuHemiRight):
            option.setChecked(option is sender)
        for window in self.displayedWindows:
            if len(self.selectedAtlasRegions[window])>0:
                self.displayImage([window])
            
    def rotateAnnotationData(self):
        if self.atlasAnnotationData is not None:
            for angle,axes in zip(self.rotationAngle,self.rotationAxes):
                self.atlasAnnotationData = scipy.ndimage.interpolation.rotate(self.atlasAnnotationData,angle,axes,order=0)
            
    def resetAnnotationData(self):
        self.clearAtlasRegions()
        self.atlasAnnotationData = self.atlasAnnotationRegions = None
                
    def normRegionLevels(self):
        if len(self.selectedAtlasRegions[self.selectedWindow])>0:
            mask = np.in1d(self.atlasAnnotationData,self.selectedAtlasRegionIDs[self.selectedWindow][0]).reshape(self.atlasAnnotationData.shape)
            if self.atlasMenuHemiLeft.isChecked():
                mask[:,mask.shape[1]//2:] = 0
            elif self.atlasMenuHemiRight.isChecked():
                mask[:,:mask.shape[1]//2] = 0
            for fileInd in set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex):
                for ch in range(self.imageObjs[fileInd].shape[3]):
                    self.imageObjs[fileInd].levels[ch][1] = self.imageObjs[fileInd].data[:,:,:,ch][mask].max()
            self.displayImageLevels()
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            self.displayImage(windows)
        
    def setOutsideRegionZero(self):
        if len(self.selectedAtlasRegions[self.selectedWindow])>0:
            mask = np.logical_not(np.in1d(self.atlasAnnotationData,self.selectedAtlasRegionIDs[self.selectedWindow][0]).reshape(self.atlasAnnotationData.shape))
            if self.atlasMenuHemiLeft.isChecked():
                mask[:,mask.shape[1]//2:] = 1
            elif self.atlasMenuHemiRight.isChecked():
                mask[:,:mask.shape[1]//2] = 1
            for fileInd in set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex):
                for ch in range(self.imageObjs[fileInd].shape[3]):
                    self.imageObjs[fileInd].data[:,:,:,ch][mask] = 0
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            self.displayImage(windows)
        
    def mainWinKeyPressCallback(self,event):
        key = event.key()
        modifiers = self.app.keyboardModifiers()
        moveKeys = (QtCore.Qt.Key_Down,QtCore.Qt.Key_Up,QtCore.Qt.Key_Left,QtCore.Qt.Key_Right,QtCore.Qt.Key_Minus,QtCore.Qt.Key_Equal)
        if key in (QtCore.Qt.Key_Comma,QtCore.Qt.Key_Period):
            if self.sliceButton.isChecked() and not self.view3dCheckbox.isChecked():
                axis = self.imageShapeIndex[self.selectedWindow][2]
                imgInd = self.imageIndex[self.selectedWindow][axis]
                if int(modifiers & QtCore.Qt.AltModifier)>0:
                    # alt + comma (<)/period (>): swap current image with previous/next image
                    if key==QtCore.Qt.Key_Comma and imgInd>self.imageRange[self.selectedWindow][axis][0]:
                        swapInd = [imgInd-1,imgInd]
                        imgInd -= 1
                    elif key==QtCore.Qt.Key_Period and imgInd<self.imageRange[self.selectedWindow][axis][1]:
                        swapInd = [imgInd,imgInd+1]
                        imgInd += 1
                    else:
                        return
                    for fileInd in self.checkedFileIndex[self.selectedWindow]:
                        d = self.imageObjs[fileInd].data
                        if axis==2:
                            d[:,:,swapInd] = d[:,:,swapInd[::-1]]
                        elif axis==1:
                            d[:,swapInd] = d[:,swapInd[::-1],:]
                        else:
                            d[swapInd] = d[swapInd[::-1]]
                    self.imageNumEditBoxes[axis].setText(str(imgInd+1))
                    self.imageIndex[self.selectedWindow][axis] = imgInd
                else:
                    # comma (<)/period (>): show previous/next image
                    if key==QtCore.Qt.Key_Comma:
                        self.setImageNum(axis,imgInd-1)
                    else:
                        self.setImageNum(axis,imgInd+1)        
        elif key==QtCore.Qt.Key_W:
            self.setViewBoxRange(self.displayedWindows)
        elif key==QtCore.Qt.Key_L and int(modifiers & QtCore.Qt.AltModifier)>0:
            self.analysisMenuPointsLock.setChecked(not self.analysisMenuPointsLock.isChecked())
        elif self.stitchCheckbox.isChecked():
            # arrow or plus/minus keys: move stitch position of selected images
            if key in moveKeys:
                windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
                fileInd = list(set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex))
                moveAxis,moveDist = self.getMoveParams(self.selectedWindow,key,modifiers,flipVert=True)
                self.stitchPos[windows,fileInd,moveAxis] += moveDist
                self.updateStitchShape(windows)
                self.displayImage(windows)
        elif key==QtCore.Qt.Key_F and int(modifiers & QtCore.Qt.AltModifier)>0:
            # alt + F: flip image horizontally
            axis = self.imageShapeIndex[self.selectedWindow][1]
            imgAxis = self.imageShapeIndex[self.selectedWindow][2]
            imgInd = self.imageIndex[self.selectedWindow][imgAxis]
            for f in (set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex)):
                self.imageObjs[f].flip(axis,imgAxis,imgInd)
                self.displayImage(self.getAffectedWindows())
        elif self.markedPoints[self.selectedWindow] is not None and int(modifiers & QtCore.Qt.AltModifier)>0:
            if key in (QtCore.Qt.Key_0,QtCore.Qt.Key_1)+moveKeys:
                axis = self.imageShapeIndex[self.selectedWindow][2]
                imgInd = self.imageIndex[self.selectedWindow][axis]
                rows = np.where(self.markedPoints[self.selectedWindow][:,axis].round()==imgInd)[0]
                if rows.size>2:
                    pts = self.markedPoints[self.selectedWindow][rows]
                    shape = tuple(self.imageShape[self.selectedWindow][i] for i in self.imageShapeIndex[self.selectedWindow][:2])
                    mask = np.zeros(shape,dtype=np.uint8)
                    cv2.fillPoly(mask,[pts.astype(int)[:,self.imageShapeIndex[self.selectedWindow][1::-1]]],255)               
                    if key in (QtCore.Qt.Key_0,QtCore.Qt.Key_1):
                        # alt + 0/1: turn pixels within polygon black/white
                        mask = mask.astype(bool)
                        if int(modifiers & QtCore.Qt.ControlModifier)>0:
                            mask = np.logical_not(mask,out=mask)
                        val = 0 if key==QtCore.Qt.Key_0 else self.levelsMax[self.selectedWindow]
                        for fileInd in self.checkedFileIndex[self.selectedWindow]:
                            for ch in range(self.imageObjs[fileInd].shape[3]):
                                if axis==2:
                                    data = self.imageObjs[fileInd].data[:,:,imgInd,ch]
                                elif axis==1:
                                    data = self.imageObjs[fileInd].data[:,imgInd,:,ch]
                                else:
                                    data = self.imageObjs[fileInd].data[imgInd,:,:,ch]
                                data[mask] = val
                    else:
                        moveAxis,dist = self.getMoveParams(self.selectedWindow,key,modifiers,True)
                        if key in moveKeys[:4]:
                            # alt + arrow key: move pixels within polygon
                            if dist<0:
                                minPt = int(pts[:,moveAxis].min())
                                if minPt==0:
                                    return
                                elif minPt+dist<0:
                                    dist = -minPt
                            else:
                                maxPt = int(pts[:,moveAxis].max())
                                if maxPt==shape[moveAxis]-1:
                                    return
                                elif maxPt+dist>=shape[moveAxis]:
                                    dist = shape[moveAxis]-1-maxPt
                            mask = mask.astype(bool)
                            shiftMask = np.roll(mask,dist,moveAxis)
                            for fileInd in self.checkedFileIndex[self.selectedWindow]:
                                for ch in range(self.imageObjs[fileInd].shape[3]):
                                    if axis==2:
                                        data = self.imageObjs[fileInd].data[:,:,imgInd,ch]
                                    elif axis==1:
                                        data = self.imageObjs[fileInd].data[:,imgInd,:,ch]
                                    else:
                                        data = self.imageObjs[fileInd].data[imgInd,:,:,ch]
                                    shiftData = data[mask].copy()
                                    data[mask] = 0
                                    data[shiftMask] = shiftData
                            self.markedPoints[self.selectedWindow][rows,moveAxis] += dist
                            cols = [moveAxis]
                        else:
                            # alt + plus/minus keys: rotate pixels within polygon
                            angle = -dist/10
                            rotMat = cv2.getRotationMatrix2D(tuple(s//2 for s in shape[::-1]),angle,1)
                            rotMask = cv2.warpAffine(mask,rotMat,shape[1::-1])
                            mask = mask.astype(bool)
                            rotMask = rotMask.astype(bool)
                            for fileInd in self.checkedFileIndex[self.selectedWindow]:
                                for ch in range(self.imageObjs[fileInd].shape[3]):
                                    if axis==2:
                                        data = self.imageObjs[fileInd].data[:,:,imgInd,ch]
                                    elif axis==1:
                                        data = self.imageObjs[fileInd].data[:,imgInd,:,ch]
                                    else:
                                        data = self.imageObjs[fileInd].data[imgInd,:,:,ch]
                                    rotData = cv2.warpAffine(data,rotMat,shape[::-1])
                                    data[mask] = 0
                                    data[rotMask] = rotData[rotMask]
                            rotMat[[0,1],[1,0]] *= -1
                            rotMat[:,2] = rotMat[::-1,2]
                            cols = self.imageShapeIndex[self.selectedWindow][:2]
                            self.markedPoints[self.selectedWindow][rows[:,None],cols] = cv2.transform(pts[:,cols][:,None,:],rotMat).squeeze()
                        appendToHistory = True
                        for p in self.localAdjustHistory[self.selectedWindow]:
                            if np.all(pts==p[1]):
                                p[1] = self.markedPoints[self.selectedWindow][rows]
                                appendToHistory = False
                                break
                        if appendToHistory:
                            self.localAdjustHistory[self.selectedWindow].append(np.stack((pts,self.markedPoints[self.selectedWindow][rows])))
                        for row in rows:
                            for col in cols:
                                ind = col if col==2 else int(not col)
                                self.markPointsTable.item(row,ind).setText(str(self.markedPoints[self.selectedWindow][row,col]+1))
                    self.displayImage()
        elif self.selectedPoints is not None:
            if key in (QtCore.Qt.Key_Delete,QtCore.Qt.Key_Backspace)+moveKeys:
                windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
                for window in windows:
                    imgAxis = self.imageShapeIndex[window][2]
                    if round(self.markedPoints[window][self.selectedPoints[0],imgAxis])==self.imageIndex[window][imgAxis]:
                        if key in (QtCore.Qt.Key_Delete,QtCore.Qt.Key_Backspace):
                            # delete key: delete selected points
                            if not self.analysisMenuPointsLock.isChecked():
                                if int(modifiers & QtCore.Qt.ControlModifier)>0:
                                    self.clearMarkedPoints()
                                else:
                                    self.deleteSelectedPoints()
                        elif key in moveKeys[:4]:
                            # arrow keys: move selected points
                            moveAxis,moveDist = self.getMoveParams(window,key,modifiers,True)
                            self.markedPoints[window][self.selectedPoints,moveAxis] += moveDist
                            if window==self.selectedWindow:
                                for point in self.selectedPoints:
                                    ind = 2 if moveAxis==2 else int(not moveAxis)
                                    self.markPointsTable.item(point,ind).setText(str(self.markedPoints[window][point,moveAxis]+1))
                            self.plotMarkedPoints([window])
                        else:
                            if int(modifiers & QtCore.Qt.ControlModifier)>0:
                                # shift + plus/minus keys: stretch points
                                stretch = 0.99 if key==QtCore.Qt.Key_Minus else 1.01
                                self.markPointsStretchFactor *= stretch
                                self.stretchPoints(stretch)
                            else:
                                # plus/minus keys: increase/decrease point size if any visible points
                                if key==QtCore.Qt.Key_Minus:
                                    if self.markPointsSize>1:
                                        self.markPointsSize -= 1
                                else:
                                    self.markPointsSize += 1
                                self.plotMarkedPoints(self.displayedWindows)                
                    
    def getMoveParams(self,window,key,modifiers,flipVert=False):
        down,up = QtCore.Qt.Key_Down,QtCore.Qt.Key_Up
        if flipVert:
            up,down = down,up
        if key in (down,up):
            axis = self.imageShapeIndex[window][0]
        elif key in (QtCore.Qt.Key_Left,QtCore.Qt.Key_Right):
            axis = self.imageShapeIndex[window][1]
        else: # minus,plus
            axis = self.imageShapeIndex[window][2]
        if int(modifiers & QtCore.Qt.ShiftModifier)>0:
            dist = 10
        elif int(modifiers & QtCore.Qt.ControlModifier)>0:
            dist = 0.1
        else:
            dist = 1
        if key in (down,QtCore.Qt.Key_Left,QtCore.Qt.Key_Minus):
            dist *= -1
        return axis,dist
            
    def window1ClickCallback(self,event):
        self.imageClickCallback(event,window=0)
    
    def window2ClickCallback(self,event):
        self.imageClickCallback(event,window=1)
        
    def window3ClickCallback(self,event):
        self.imageClickCallback(event,window=2)
        
    def window4ClickCallback(self,event):
        self.imageClickCallback(event,window=3)
        
    def window1DoubleClickCallback(self,event):
        self.imageDoubleClickCallback(event,window=0)
    
    def window2DoubleClickCallback(self,event):
        self.imageDoubleClickCallback(event,window=1)
        
    def window3DoubleClickCallback(self,event):
        self.imageDoubleClickCallback(event,window=2)
        
    def window4DoubleClickCallback(self,event):
        self.imageDoubleClickCallback(event,window=3)
            
    def imageClickCallback(self,event,window):
        x,y = int(event.pos().x()),int(event.pos().y())
        if not self.viewChannelsCheckbox.isChecked():
            self.windowListbox.setCurrentRow(window)
        if event.button()==QtCore.Qt.LeftButton:
            if self.view3dCheckbox.isChecked():
                for line,pos in zip(self.view3dSliceLines[window],(y,x)):
                    line.setValue(pos)
                self.updateView3dLines(axes=self.imageShapeIndex[window][:2],position=(y,x))
        else:
            if self.markedPoints[window] is not None:
                axis = self.imageShapeIndex[window][2]
                rows = np.where(self.markedPoints[window][:,axis].round()==self.imageIndex[window][axis])[0]
                if len(rows)>0:
                    self.setSelectedPoints([rows[np.argmin(np.sum((self.markedPoints[window][rows,:][:,self.imageShapeIndex[window][:2]]-[y,x])**2,axis=1)**0.5)]])
        
    def imageDoubleClickCallback(self,event,window):
        if not self.viewChannelsCheckbox.isChecked():
            self.windowListbox.setCurrentRow(window)
        if event.button()==QtCore.Qt.LeftButton:
            if not self.analysisMenuPointsLock.isChecked():
                x,y = (p*self.displayDownsample[window] for p in (event.pos().x(),event.pos().y()))
                newPoint = np.array([y,x,self.imageIndex[window][self.imageShapeIndex[window][2]]])[list(self.imageShapeIndex[window])]
                windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [window]
                for window in windows:
                    self.markedPoints[window] = newPoint[None,:] if self.markedPoints[window] is None else np.concatenate((self.markedPoints[window],newPoint[None,:]))
                    if window==self.selectedWindow:
                        self.fillPointsTable(append=True)
                self.setSelectedPoints([self.markedPoints[window].shape[0]-1])
                self.plotMarkedPoints(windows)
        else:
            if self.markedPoints[window] is not None:
                if self.markedPoints[window] is not None:
                    axis = self.imageShapeIndex[window][2]
                    rows = np.where(self.markedPoints[window][:,axis].round()==self.imageIndex[window][axis])[0]
                    if len(rows)>0:
                        self.setSelectedPoints(rows)
        
    def fileListboxSelectionCallback(self):
        self.selectedFileIndex = getSelectedItemsIndex(self.fileListbox)
        self.displayImageLevels()
        
    def fileListboxItemClickedCallback(self,item):
        fileInd = self.fileListbox.indexFromItem(item).row()
        checked = self.checkedFileIndex[self.selectedWindow]
        windows = self.displayedWindows if self.viewChannelsCheckbox.isChecked() or self.view3dCheckbox.isChecked() else [self.selectedWindow]
        if item.checkState()==QtCore.Qt.Checked and fileInd not in checked:
            if len(checked)>0 or self.linkWindowsCheckbox.isChecked():
                if self.imageObjs[fileInd].dtype!=self.imageObjs[checked[0]].dtype:
                    item.setCheckState(QtCore.Qt.Unchecked)
                    raise Exception('Images displayed in the same window or linked windows must be the same data type')
                if not self.stitchCheckbox.isChecked() and self.imageObjs[fileInd].shape[:3]!=self.imageObjs[checked[0]].shape[:3]:
                    item.setCheckState(QtCore.Qt.Unchecked)
                    raise Exception('Images displayed in the same window or linked windows must be the same shape unless stitching')
            checked.append(fileInd)
            checked.sort()
            if len(checked)>1:
                if self.imageObjs[fileInd].shape[3]>self.channelListbox.count():
                    self.updateChannelList()
                    if self.viewChannelsCheckbox.isChecked():
                        self.setViewChannelsOn()
            else:
                self.displayedWindows.append(self.selectedWindow)
                self.displayedWindows.sort()
            if self.stitchCheckbox.isChecked():
                self.stitchPos[windows,fileInd,:] = 0
                self.updateStitchShape(windows)
                self.displayImageLevels()
                self.displayImage(windows)
            else:
                if len(checked)>1:
                    self.displayImageLevels()
                    self.displayImage(windows)
                elif self.view3dCheckbox.isChecked():
                    self.setView3dOn()
                else:
                    self.initImageWindow()
        elif item.checkState()!=QtCore.Qt.Checked and fileInd in checked:
            checked.remove(fileInd)
            if len(checked)<1:
                if self.viewChannelsCheckbox.isChecked():
                    self.setViewChannelsOff()
                elif self.view3dCheckbox.isChecked():
                    self.setView3dOff()
                self.resetImageWindow()
            else:
                self.updateChannelList()
                if fileInd in self.selectedFileIndex:
                    self.displayImageLevels()
                if self.stitchCheckbox.isChecked():
                    self.stitchPos[windows,fileInd,:] = np.nan
                    self.updateStitchShape(windows)
                self.displayImage(windows)                    
                    
    def moveFileDownButtonCallback(self):
        for i,fileInd in reversed(list(enumerate(self.selectedFileIndex))):
            if fileInd<self.fileListbox.count()-1 and (i==len(self.selectedFileIndex)-1 or self.selectedFileIndex[i+1]-fileInd>1):
                item = self.fileListbox.takeItem(fileInd)
                self.fileListbox.insertItem(fileInd+1,item)
                self.fileListbox.setItemSelected(item,True)
                for checked in self.checkedFileIndex:
                    if fileInd in checked and fileInd+1 in checked:
                        n = checked.index(fileInd)
                        checked[n],checked[n+1] = checked[n+1],checked[n]
                    elif fileInd in checked:
                        checked[checked.index(fileInd)] += 1
                    elif fileInd+1 in checked:
                        checked[checked.index(fileInd+1)] -= 1
                self.imageObjs[fileInd],self.imageObjs[fileInd+1] = self.imageObjs[fileInd+1],self.imageObjs[fileInd]
                if self.stitchCheckbox.isChecked():
                    self.stitchPos[:,[fileInd,fileInd+1]] = self.stitchPos[:,[fileInd+1,fileInd]]
        self.displayImage(self.getAffectedWindows())
    
    def moveFileUpButtonCallback(self):
        for i,fileInd in enumerate(self.selectedFileIndex[:]):
            if fileInd>0 and (i==0 or fileInd-self.selectedFileIndex[i-1]>1):
                item = self.fileListbox.takeItem(fileInd)
                self.fileListbox.insertItem(fileInd-1,item)
                self.fileListbox.setItemSelected(item,True)
                for checked in self.checkedFileIndex:
                    if fileInd in checked and fileInd-1 in checked:
                        n = checked.index(fileInd)
                        checked[n-1],checked[n] = checked[n],checked[n-1]
                    elif fileInd in checked:
                        checked[checked.index(fileInd)] -= 1
                    elif fileInd-1 in checked:
                        checked[checked.index(fileInd-1)] += 1
                self.imageObjs[fileInd-1],self.imageObjs[fileInd] = self.imageObjs[fileInd],self.imageObjs[fileInd-1]
                if self.stitchCheckbox.isChecked():
                    self.stitchPos[:,[fileInd-1,fileInd]] = self.stitchPos[:,[fileInd,fileInd-1]]
        self.displayImage(self.getAffectedWindows())
    
    def removeFileButtonCallback(self):
        windows = self.getAffectedWindows()
        for fileInd in reversed(self.selectedFileIndex):
            for checked in self.checkedFileIndex:
                if fileInd in checked:
                    checked.remove(fileInd)
            self.imageObjs.remove(self.imageObjs[fileInd])
            self.fileListbox.takeItem(fileInd)
        self.stitchPos = np.delete(self.stitchPos,self.selectedFileIndex,axis=1)
        if self.stitchPos.shape[1]<1:
            self.stitchPos = np.full((self.numWindows,1,3),np.nan)
        if self.stitchCheckbox.isChecked():
            self.updateStitchShape(windows)
        self.selectedFileIndex = []
        for window in windows:
            if len(self.checkedFileIndex[window])<1:
                if self.viewChannelsCheckbox.isChecked():
                    self.setViewChannelsOff()
                elif self.view3dCheckbox.isChecked():
                    self.setView3dOff()
                self.resetImageWindow(window)
            else:
                if window==self.selectedWindow:
                    self.updateChannelList()
                    self.displayImageLevels()
                self.displayImage([window])
                
    def setStitchOverlayMode(self):
        sender = self.mainWin.sender()
        for option in (self.imageMenuStitchOverlayMax,self.imageMenuStitchOverlayReplace):
            option.setChecked(option is sender)
        if self.stitchCheckbox.isChecked():
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            self.displayImage(windows)
            
    def setStitchTileMode(self):
        sender = self.mainWin.sender()
        for option in (self.imageMenuStitchTileXY,self.imageMenuStitchTileZ):
            option.setChecked(option is sender)
            
    def loadStitchPositions(self):
        filePath,fileType = QtWidgets.QFileDialog.getOpenFileName(self.mainWin,'Choose File',self.fileOpenPath,'*.npy')
        if filePath=='':
            return
        self.fileOpenPath = os.path.dirname(filePath)
        self.stitchPos[self.selectedWindow] = np.load(filePath)
        self.initStitch()
    
    def saveStitchPositions(self):
        filePath,fileType = QtWidgets.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.npy')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        np.save(filePath,self.stitchPos[self.selectedWindow])
            
    def stitchCheckboxCallback(self):
        if self.stitchCheckbox.isChecked():
            if self.linkWindowsCheckbox.isChecked():
                if not (self.viewChannelsCheckbox.isChecked or self.view3dCheckbox.isChecked()):
                    self.stitchCheckbox.setChecked(False)
                    raise Exception('Stitching can not be initiated while link windows mode is on unless channel view or view 3D is selected')
            elif len(self.selectedFileIndex)<1:
                self.stitchCheckbox.setChecked(False)
                return
            else:
                for i in range(self.fileListbox.count()):
                    if i in self.selectedFileIndex:
                        self.fileListbox.item(i).setCheckState(QtCore.Qt.Checked)
                    else:
                        self.fileListbox.item(i).setCheckState(QtCore.Qt.Unchecked)
                self.checkedFileIndex[self.selectedWindow] = self.selectedFileIndex[:]
            self.stitchPos[self.selectedWindow] = np.nan
            useStagePos = all([self.imageObjs[i].position is not None for i in self.selectedFileIndex])
            pos = [0,0,0]
            n = 0
            for i in self.selectedFileIndex:
                if useStagePos:
                    self.stitchPos[self.selectedWindow,i,:] = self.imageObjs[i].position
                else:
                    if self.imageMenuStitchTileXY.isChecked():
                        if n>math.floor(len(self.selectedFileIndex)**0.5):
                            n = 0
                            pos[0] += self.imageObjs[i].shape[0]
                            pos[1] = 0
                        elif n>0:
                            pos[1] += self.imageObjs[i].shape[1]
                    elif n>1:
                        pos[2] = n-1
                    n += 1    
                    self.stitchPos[self.selectedWindow,i,:] = pos
            self.initStitch()
        else:
            self.stitchState[self.selectedWindow] = False
            if len(self.checkedFileIndex[self.selectedWindow])>1:
                for i in self.checkedFileIndex[self.selectedWindow][1:]:
                    self.fileListbox.item(i).setCheckState(QtCore.Qt.Unchecked)
                del(self.checkedFileIndex[self.selectedWindow][1:])
            if self.viewChannelsCheckbox.isChecked() or self.view3dCheckbox.isChecked():
                self.displayImageInfo()
                if self.viewChannelsCheckbox.isChecked():
                    self.setViewChannelsOn()
                else:
                    self.setView3dOn()
            else:
                self.initImageWindow()
                
    def initStitch(self):
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.stitchState[window] = True
            self.holdStitchRange[window] = False
            if window!=self.selectedWindow:
                self.stitchPos[window] = self.stitchPos[self.selectedWindow]
        self.updateStitchShape(windows)
        self.updateChannelList()
        self.displayImageLevels()
        self.displayImage(windows)
    
    def updateStitchShape(self,windows=None):
        if windows is None:
            windows = [self.selectedWindow]
        for window in windows:
            self.stitchPos[window] -= np.nanmin(self.stitchPos[window],axis=0)
            tileShapes = np.array([self.imageObjs[i].shape[:3] for i in self.checkedFileIndex[window]])
            self.imageShape[window] = (self.stitchPos[self.selectedWindow,self.checkedFileIndex[window],:]+tileShapes).max(axis=0).astype(int)
            if self.holdStitchRange[window]:
                for axis in (0,1,2):
                    if self.imageRange[window][axis][1]>=self.imageShape[window][axis]-1:
                        self.setImageRange(axes=[axis],rangeInd=1,window=window)
            else:
                self.setImageRange(window=window)
        self.setViewBoxRangeLimits(windows)
        self.setViewBoxRange(windows)
        self.displayImageRange()
            
    def windowListboxCallback(self):
        self.setActiveWindow(self.windowListbox.currentRow())
        
    def setActiveWindow(self,window):
        self.selectedWindow = window
        for i in range(self.fileListbox.count()):
            if i in self.checkedFileIndex[window]:
                self.fileListbox.item(i).setCheckState(QtCore.Qt.Checked)
            else:
                self.fileListbox.item(i).setCheckState(QtCore.Qt.Unchecked)
        self.downsampleEdit.setText(str(self.displayDownsample[window]))
        self.sliceProjButtons[self.sliceProjState[window]].setChecked(True)
        self.xyzButtons[self.xyzState[window]].setChecked(True)
        self.normDisplayCheckbox.setChecked(self.normState[window])
        self.showBinaryCheckbox.setChecked(self.showBinaryState[window])
        self.stitchCheckbox.setChecked(self.stitchState[window])
        for ind,region in enumerate(self.atlasRegionMenu):
            region.setChecked(ind in self.selectedAtlasRegions[window])
        self.clearPointsTable()
        self.fillPointsTable()
        self.setSelectedPoints(None)
        isAligned = self.alignRefWindow[window] is not None
        self.alignCheckbox.setChecked(isAligned)
        alignRange = [str(self.alignRange[window][i]+1) if self.alignRange[window][i] is not None else '' for i in (0,1)]
        self.alignStartEdit.setText(alignRange[0])
        self.alignEndEdit.setText(alignRange[1])
        self.displayImageInfo()
    
    def linkWindowsCheckboxCallback(self):
        if self.linkWindowsCheckbox.isChecked():
            if self.stitchCheckbox.isChecked():
                self.linkWindowsCheckbox.setChecked(False)
                raise Exception('Linking windows is not allowed while stitch mode is on unless channel view or 3D view is selected')
            if len(self.displayedWindows)>1:
                imageObj = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]]
                otherWindows = [w for w in self.displayedWindows if w!=self.selectedWindow]
                if any(self.imageObjs[self.checkedFileIndex[window][0]].shape[:3]!=imageObj.shape[:3] for window in otherWindows):
                    self.linkWindowsCheckbox.setChecked(False)
                    raise Exception('Image shapes must be equal when linking windows')
                for window in otherWindows:
                    self.imageRange[window] = self.imageRange[self.selectedWindow][:]
                self.setViewBoxRange(self.displayedWindows)
                
    def getAffectedWindows(self,channels=None):
        return [window for window in self.displayedWindows if any(i in self.selectedFileIndex for i in self.checkedFileIndex[window]) and (channels is None or any(ch in channels for ch in self.selectedChannels[window]))]
        
    def channelListboxCallback(self):
        if self.viewChannelsCheckbox.isChecked():
            self.viewChannelsSelectedCh = self.channelListbox.currentRow()
            self.displayImageLevels()
        else:
            channels = getSelectedItemsIndex(self.channelListbox)
            self.selectedChannels[self.selectedWindow] = channels
            self.displayImageLevels()
            self.displayImage()
        
    def updateChannelList(self):
        self.channelListbox.blockSignals(True)
        self.channelListbox.clear()
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            numCh = max(self.imageObjs[i].shape[3] for i in self.checkedFileIndex[self.selectedWindow])
            for ch in range(numCh):
                item = QtWidgets.QListWidgetItem('Ch '+str(ch+1),self.channelListbox)
                if ch in self.selectedChannels[self.selectedWindow]:
                    item.setSelected(True)
        self.channelListbox.blockSignals(False)
        
    def channelColorMenuCallback(self):
        menuInd = self.channelColorMenu.currentIndex()
        if menuInd>0:
            rgbInd = ((0,1,2),(0,),(1,),(2,),(0,2))[menuInd-1]
            self.channelColorMenu.setCurrentIndex(0)
            channels = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannels[self.selectedWindow]
            for fileInd in self.selectedFileIndex:
                for ch in channels:
                    if ch<self.imageObjs[fileInd].shape[3]:
                        self.imageObjs[fileInd].rgbInd[ch] = rgbInd
            self.displayImage(self.getAffectedWindows(channels))
        
    def sliceProjButtonCallback(self):
        isSlice = self.sliceButton.isChecked()
        if self.view3dCheckbox.isChecked():
            for windowLines in self.view3dSliceLines:
                for line in windowLines:
                    line.setVisible(isSlice)
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.sliceProjState[window] = int(not isSlice)
        self.displayImage(windows)
    
    def xyzButtonCallback(self):
        if self.zButton.isChecked():
            state = 2
            shapeInd = (0,1,2)
        elif self.yButton.isChecked():
            state = 1
            shapeInd = (2,1,0)
        else:
            state = 0
            shapeInd = (0,2,1)
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.xyzState[window] = state
            self.imageShapeIndex[window] = shapeInd
        self.setViewBoxRangeLimits(windows)
        self.setViewBoxRange(windows)
        self.displayImage(windows)
        
    def viewChannelsCheckboxCallback(self):
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            if self.viewChannelsCheckbox.isChecked():
                if self.view3dCheckbox.isChecked():
                    self.setView3dOff()
                self.setViewChannelsOn()
            else:
                self.setViewChannelsOff()
                
    def setViewChannelsOn(self):
        self.viewChannelsCheckbox.setChecked(True)
        self.channelListbox.blockSignals(True)
        self.viewChannelsSelectedCh = self.selectedChannels[self.selectedWindow][0]
        self.channelListbox.setCurrentRow(self.viewChannelsSelectedCh)
        self.channelListbox.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.channelListbox.blockSignals(False)
        numCh = min(self.numWindows,max(self.imageObjs[i].shape[3] for i in self.checkedFileIndex[self.selectedWindow]))
        self.selectedChannels[:numCh] = [[ch] for ch in range(numCh)]
        for window in range(numCh):
            self.xyzState[window] = self.xyzState[self.selectedWindow]
            self.imageShapeIndex[window] = self.imageShapeIndex[self.selectedWindow]
            self.imageIndex[window] = self.imageIndex[self.selectedWindow]
        self.setLinkedViewOn(numWindows=numCh)
        
    def setViewChannelsOff(self):
        self.viewChannelsCheckbox.setChecked(False)
        self.channelListbox.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setLinkedViewOff()
    
    def view3dCheckboxCallback(self):
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            if self.view3dCheckbox.isChecked():
                if self.viewChannelsCheckbox.isChecked():
                    self.setViewChannelsOff()
                self.setView3dOn()
            else:
                self.setView3dOff()
            
    def setView3dOn(self):
        self.view3dCheckbox.setChecked(True)
        self.xyzGroupBox.setEnabled(False)
        self.selectedChannels[:3] = [self.selectedChannels[self.selectedWindow] for _ in range(3)]
        self.xyzState[:3] = [2,1,0]
        self.imageShapeIndex[:3] = [(0,1,2),(2,1,0),(0,2,1)]
        self.imageIndex[:3] = [[(r[1]-r[0])//2 for r in self.imageRange[0]] for _ in range(3)]
        for i,editBox in enumerate(self.imageNumEditBoxes):
            editBox.setText(str(self.imageIndex[self.selectedWindow][i]))
        isSlice = self.sliceButton.isChecked()
        self.ignoreImageRangeChange = True
        for window in range(3):
            for line,ax in zip(self.view3dSliceLines[window],self.imageShapeIndex[window][:2]):
                line.setValue(self.imageIndex[window][ax])
                line.setBounds(self.imageRange[self.selectedWindow][ax])
                line.setVisible(isSlice)
                self.imageViewBox[window].addItem(line)
        self.ignoreImageRangeChange = False
        self.setLinkedViewOn(numWindows=3)
            
    def setView3dOff(self):
        self.view3dCheckbox.setChecked(False)
        for window in self.displayedWindows:
            for line in self.view3dSliceLines[window]:
                self.imageViewBox[window].removeItem(line)
        self.xyzGroupBox.setEnabled(True)
        self.setLinkedViewOff()
        
    def view3dSliceLineDragged(self):
        sender = self.mainWin.sender()
        for window,lines in enumerate(self.view3dSliceLines):
            if sender in lines:
                axis = self.imageShapeIndex[window][lines.index(sender)]
                break 
        self.updateView3dLines([axis],[int(sender.value())])
        
    def updateView3dLines(self,axes,position):
        for window in self.displayedWindows:
            shapeInd = self.imageShapeIndex[window][:2]
            for axis,pos in zip(axes,position):
                if axis in shapeInd:
                    self.view3dSliceLines[window][shapeInd.index(axis)].setValue(pos)
                elif position is not None:
                    self.imageNumEditBoxes[axis].setText(str(pos+1))
                    self.imageIndex[window][axis] = pos
                    self.displayImage([window])
                    
    def setLinkedViewOn(self,numWindows):
        self.windowListbox.blockSignals(True)
        self.windowListbox.setCurrentRow(0)
        self.windowListbox.blockSignals(False)
        self.windowListbox.setEnabled(False)
        self.linkWindowsCheckbox.setEnabled(False)
        self.linkWindowsCheckbox.setChecked(True)
        for window in range(numWindows):
            self.checkedFileIndex[window] = self.checkedFileIndex[self.selectedWindow]
            self.displayDownsample[window] = self.displayDownsample[self.selectedWindow]
            self.sliceProjState[window] = self.sliceProjState[self.selectedWindow]
            self.imageShape[window] = self.imageShape[self.selectedWindow]
            self.imageRange[window] = self.imageRange[self.selectedWindow]
            self.normState[window] = self.normState[self.selectedWindow]
            self.showBinaryState[window] = self.showBinaryState[self.selectedWindow]
            self.stitchState[window] = self.stitchState[self.selectedWindow]
            self.selectedAtlasRegions[window] = self.selectedAtlasRegions[self.selectedWindow]
            self.selectedAtlasRegionIDs[window] = self.selectedAtlasRegionIDs[self.selectedWindow]
            self.markedPoints[window] = self.markedPoints[self.selectedWindow]
        if self.stitchState[self.selectedWindow]:
            self.stitchPos[:numWindows] = self.stitchPos[self.selectedWindow]
        for window in self.displayedWindows:
            if window>numWindows-1:
                self.resetImageWindow(window)
        self.selectedWindow = 0
        self.displayedWindows = list(range(numWindows))
        self.setViewBoxRangeLimits(self.displayedWindows)
        self.setViewBoxRange(self.displayedWindows)
        self.displayImage(self.displayedWindows)
        isZoom = self.zoomPanButton.isChecked()
        for window in self.displayedWindows:
            self.imageViewBox[window].setZValue(1)
            self.imageViewBox[window].setMouseEnabled(x=isZoom,y=isZoom)
            
    def setLinkedViewOff(self):
        if len(self.displayedWindows)>1:
            for window in self.displayedWindows[1:]:
                self.checkedFileIndex[window] = []
                self.resetImageWindow(window)
        self.windowListbox.setEnabled(True)
        self.linkWindowsCheckbox.setChecked(False)
        self.linkWindowsCheckbox.setEnabled(True)
        self.setViewBoxRange()
        
    def imageNumEditCallback(self):
        self.setImageNum(axis=self.imageNumEditBoxes.index(self.mainWin.sender()))
        
    def setImageNum(self,axis,imgInd=None):
        if imgInd is None:
            imgInd = int(float(self.imageNumEditBoxes[axis].text()))-1
        if imgInd<self.imageRange[self.selectedWindow][axis][0]:
            imgInd = self.imageRange[self.selectedWindow][axis][0]
        elif imgInd>self.imageRange[self.selectedWindow][axis][1]:
            imgInd = self.imageRange[self.selectedWindow][axis][1]
        if self.view3dCheckbox.isChecked():
            self.updateView3dLines([axis],[imgInd])
        else:
            self.imageNumEditBoxes[axis].setText(str(imgInd+1))
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            for window in windows:
                self.imageIndex[window][axis] = imgInd
            self.displayImage(windows)
            if not self.linkWindowsCheckbox.isChecked():
                self.alignWindows(self.selectedWindow,axis)
            
    def zoomPanButtonCallback(self):
        isOn = self.zoomPanButton.isChecked()
        if isOn:
            self.roiButton.setChecked(False)
        for window in self.displayedWindows:
            if isOn:
                self.imageViewBox[window].setMouseMode(pg.ViewBox.PanMode)
            self.imageViewBox[window].setMouseEnabled(x=isOn,y=isOn)
            
    def roiButtonCallback(self):
        isOn = self.roiButton.isChecked()
        if isOn:
            self.zoomPanButton.setChecked(False)
        for window in self.displayedWindows:
            if isOn:
                self.imageViewBox[window].setMouseMode(pg.ViewBox.RectMode)
            self.imageViewBox[window].setMouseEnabled(x=isOn,y=isOn)
        
    def resetViewButtonCallback(self):
        if self.selectedWindow in self.displayedWindows:
            for axis,editBoxes in enumerate(self.rangeEditBoxes):
                editBoxes[0].setText('1')
                editBoxes[1].setText(str(self.imageShape[self.selectedWindow][axis]))
            self.setImageRange()
        
    def rangeEditCallback(self):
        sender = self.mainWin.sender()
        for axis,boxes in enumerate(self.rangeEditBoxes):
            if sender in boxes:
                rangeInd = boxes.index(sender)
                break
        if rangeInd==0:
            newVal = int(float(self.rangeEditBoxes[axis][0].text()))-1
            axMin = 0
            axMax = int(float(self.rangeEditBoxes[axis][1].text()))-1
        else:
            newVal = int(float(self.rangeEditBoxes[axis][1].text()))-1
            axMin = int(float(self.rangeEditBoxes[axis][0].text()))-1
            axMax = self.imageShape[self.selectedWindow][axis]-1
        if newVal<axMin:
            newVal = axMin
        elif newVal>axMax:
            newVal = axMax
        self.rangeEditBoxes[axis][rangeInd].setText(str(newVal+1))
        self.setImageRange([newVal],[axis],rangeInd)
        
    def imageRangeChanged(self):
        if len(self.displayedWindows)<1 or self.ignoreImageRangeChange:
            return
        window = self.imageViewBox.index(self.mainWin.sender())
        newRange = [[int(i*self.displayDownsample[window]) for i in r] for r in reversed(self.imageViewBox[window].viewRange())]
        axes = self.imageShapeIndex[window][:2]
        if self.view3dCheckbox.isChecked():
            # adjust out of plain range proportionally
            zoom = [(r[1]-r[0])/(self.imageRange[window][axis][1]-self.imageRange[window][axis][0])-1 for r,axis in zip(newRange,axes)]
            zoom = min(zoom) if min(zoom)<0 else max(zoom)
            axes = self.imageShapeIndex[window]
            rng = self.imageRange[window][axes[2]]
            zoomPix = 0.5*zoom*(rng[1]-rng[0])
            rng[0] -= zoomPix
            rng[1] += zoomPix
            if rng[0]>=rng[1]:
                rng[0] -= 1
                rng[1] += 1
            rngMax = self.imageShape[window][axes[2]]-1
            rng[0] = 0 if rng[0]<0 else int(rng[0])
            rng[1] = rngMax if rng[1]>rngMax else int(rng[1])
            newRange.append(rng)
        for rng,axis in zip(newRange,axes):
            if window==self.selectedWindow or self.linkWindowsCheckbox.isChecked():
                self.rangeEditBoxes[axis][0].setText(str(rng[0]+1))
                self.rangeEditBoxes[axis][1].setText(str(rng[1]+1))
        self.setImageRange(newRange,axes,window=window)
        
    def setImageRange(self,newRange=None,axes=(0,1,2),rangeInd=slice(2),window=None):
        if window is None:
            window = self.selectedWindow
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [window]
        for window in windows:
            if self.stitchState[window]:
                self.holdStitchRange[window] = False if newRange is None and isinstance(rangeInd,slice) else True
            if newRange is None: # reset min and/or max
                newRange = [[0,self.imageShape[window][axis]-1][rangeInd] for axis in axes]
            for rng,axis in zip(newRange,axes):
                axRange = self.imageRange[window][axis]
                axRange[rangeInd] = rng
                if axRange[0]<=self.imageIndex[window][axis]<=axRange[1]:
                    imgIndChanged = False
                else:
                    imgIndChanged = True
                    if self.imageIndex[window][axis]<axRange[0]:
                        self.imageIndex[window][axis] = axRange[0]
                    else:
                        self.imageIndex[window][axis] = axRange[1]
                    if window==self.selectedWindow or self.linkWindowsCheckbox.isChecked():
                        self.imageNumEditBoxes[axis].setText(str(self.imageIndex[window][axis]+1))
                if self.view3dCheckbox.isChecked():
                    shapeInd = self.imageShapeIndex[window][:2]
                    if axis in shapeInd:
                        ind = shapeInd.index(axis)
                        if imgIndChanged:
                            self.view3dSliceLines[window][ind].setValue(self.imageIndex[window][axis])
                        self.view3dSliceLines[window][ind].setBounds(rng)
            if self.imageShapeIndex[window][2] in axes and (imgIndChanged or self.sliceProjState[window]):
                self.displayImage([window])
            if any(axis in self.imageShapeIndex[window][:2] for axis in axes):
                self.setViewBoxRange([window])
            if imgIndChanged and not self.linkWindowsCheckbox.isChecked():
                self.alignWindows(window,axis)
        
    def saveImageRange(self):
        filePath,fileType = QtWidgets.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.npy')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        np.save(filePath,self.imageRange[self.selectedWindow])
    
    def loadImageRange(self):
        filePath,fileType = QtWidgets.QFileDialog.getOpenFileName(self.mainWin,'Choose File',self.fileOpenPath,'*.npy')
        if filePath=='':
            return
        self.fileOpenPath = os.path.dirname(filePath)
        savedRange = np.load(filePath)
        for rangeBox,rng,shape in zip(self.rangeEditBoxes,savedRange,self.imageShape[self.selectedWindow]):
            if rng[0]<0:
                rng[0] = 0
            if rng[1]>shape-1:
                rng[1] = shape-1
            rangeBox[0].setText(str(rng[0]+1))
            rangeBox[1].setText(str(rng[1]+1))
        self.setImageRange(savedRange)
        
    def lowLevelLineCallback(self):
        val = self.lowLevelLine.value()
        self.lowLevelBox.blockSignals(True)
        self.lowLevelBox.setValue(val)
        self.lowLevelBox.blockSignals(False)
        self.setLowLevel(val)
         
    def highLevelLineCallback(self):
        val = self.highLevelLine.value()
        self.highLevelBox.blockSignals(True)
        self.highLevelBox.setValue(val)
        self.highLevelBox.blockSignals(False)
        self.setHighLevel(val)
        
    def lowLevelBoxCallback(self,val):
        self.lowLevelLine.setValue(val)
        self.setLowLevel(val)
    
    def highLevelBoxCallback(self,val):
        self.highLevelLine.setValue(val)
        self.setHighLevel(val)
        
    def setLowLevel(self,val):
        highRange = (val+1,self.levelsMax[self.selectedWindow])
        self.highLevelBox.setRange(highRange[0],highRange[1])
        self.highLevelLine.setBounds(highRange)
        self.setLevels(val,levelsInd=0)
    
    def setHighLevel(self,val):
        lowRange = (0,val-1)
        self.lowLevelBox.setRange(lowRange[0],lowRange[1])
        self.lowLevelLine.setBounds(lowRange)
        self.setLevels(val,levelsInd=1)
        
    def setLevels(self,newVal,levelsInd):
        channels = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannels[self.selectedWindow]
        for fileInd in set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex):
            for ch in channels:
                if ch<self.imageObjs[fileInd].shape[3]:
                    self.imageObjs[fileInd].levels[ch][levelsInd] = newVal
        self.displayImage(self.getAffectedWindows(channels))
        
    def showLevelsButtonCallback(self):
        sender = self.mainWin.sender()
        if sender==self.showNoLevelsButton:
            self.updateLevelsPlot()
        elif sender==self.showVolumeLevelsButton:
            self.displayImageLevels()
        else:
            self.displayImage()
        
    def gammaBoxCallback(self,val):
        channels = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannels[self.selectedWindow]
        for fileInd in set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex):
            for ch in channels:
                if ch<self.imageObjs[fileInd].shape[3]:
                    self.imageObjs[fileInd].gamma[ch] = val
        self.displayImage(self.getAffectedWindows(channels))
        
    def alphaBoxCallback(self,val):
        for fileInd in set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex):
            self.imageObjs[fileInd].alpha = val
        self.displayImage(self.getAffectedWindows())
        
    def resetLevelsButtonCallback(self):
        self.lowLevelLine.setValue(0)
        self.highLevelLine.setValue(self.levelsMax[self.selectedWindow])
        for box in self.levelsBoxes:
            box.blockSignals(True)
        self.lowLevelBox.setValue(0)
        self.highLevelBox.setValue(self.levelsMax[self.selectedWindow])
        self.gammaBox.setValue(1)
        self.alphaBox.setValue(1)
        for box in self.levelsBoxes:
            box.blockSignals(False)
        channels = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannels[self.selectedWindow]
        for fileInd in self.selectedFileIndex:
            for ch in channels:
                if ch<self.imageObjs[fileInd].shape[3]:
                    self.imageObjs[fileInd].levels[ch] = [0,self.levelsMax[self.selectedWindow]]
                    self.imageObjs[fileInd].gamma[ch] = 1
            self.imageObjs[fileInd].alpha = 1
        self.displayImage(self.getAffectedWindows(channels))
        
    def normDisplayCheckboxCallback(self):
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.normState[window] = self.normDisplayCheckbox.isChecked()
            if self.normState[window]:
                self.showBinaryState[window] = False
        if self.normState[self.selectedWindow] and self.showBinaryState[self.selectedWindow]:
            self.showBinaryCheckbox.setChecked(False)
        self.displayImage(windows)
        
    def showBinaryCheckboxCallback(self):
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.showBinaryState[window] = self.showBinaryCheckbox.isChecked()
            if self.showBinaryState[window]:
                self.normState[window] = False
        if self.showBinaryState[self.selectedWindow] and self.normState[self.selectedWindow]:
            self.normDisplayCheckbox.setChecked(False)
        self.displayImage(windows)
        
    def plotMarkedPoints(self,windows=None):
        if windows is None:
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow] 
        for window in windows:
            x,y,rows = self.getPlotPoints(window)
            if len(x)>0 and self.analysisMenuPointsJitter.isChecked():
                for v in np.unique(y):
                    i = y==v
                    n = i.sum()
                    if n>1:
                        x[i] += np.arange(n)-n/2+0.5
            if len(x)==0 or self.markPointsColorValues[window] is None or self.markPointsColorValues[window].shape[0]!=self.markedPoints[window].shape[0]:
                color = tuple(255*c for c in self.markPointsColor)
                pen = None if self.analysisMenuPointsLineNone.isChecked() else color
            else:
                color = [pg.mkPen(clr) for clr in (self.markPointsColorValuesRGB[rows]*255).astype(np.uint8)]
                pen = None
            self.markPointsPlot[window].setData(x=x,y=y,pen=pen,symbolSize=self.markPointsSize,symbolPen=color)
            
    def getPlotPoints(self,window):
        x = y = rows = []
        if self.markedPoints[window] is not None:
            axis = self.imageShapeIndex[window][2]
            rng = self.imageRange[window][axis] if self.sliceProjState[window] else [self.imageIndex[window][axis]]*2
            ind = self.markedPoints[window][:,axis].round()
            rows = np.logical_and(ind>=rng[0],ind<=rng[1])
            if any(rows):
                y,x = self.markedPoints[window][rows,:][:,self.imageShapeIndex[window][:2]].T/self.displayDownsample[window]
                if self.analysisMenuPointsLinePoly.isChecked():
                    x = np.append(x,x[0])
                    y = np.append(y,y[0])
        return x,y,rows
    
    def jitterPoints(self):
        self.plotMarkedPoints()
        
    def fillPointsTable(self,append=False):
        if self.markedPoints[self.selectedWindow] is not None:
            numPts = self.markedPoints[self.selectedWindow].shape[0]
            if append:
                numRows = self.markPointsTable.rowCount()
                firstRow = 0 if numRows==1 else numRows
                rows = range(firstRow,numPts)
                for row in rows:
                    if row>0:
                        self.markPointsTable.insertRow(row)
            else:
                self.markPointsTable.setRowCount(numPts)
                rows = range(numPts)
            for row in rows:
                pt = [str(round(self.markedPoints[self.selectedWindow][row,i],2)+1) for i in (1,0,2)]
                for col in range(self.markPointsTable.columnCount()):
                    if row>0:
                        item = QtWidgets.QTableWidgetItem(pt[col])
                        item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                        self.markPointsTable.setItem(row,col,item)
                    else:
                        self.markPointsTable.item(row,col).setText(pt[col])
                
    def clearPointsTable(self):
        self.markPointsTable.setRowCount(1)
        for col in range(3):
            self.markPointsTable.item(0,col).setText('')
        
    def clearMarkedPoints(self,windows=None):
        if windows is None:
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.markedPoints[window] = None
            self.markPointsColorValues[window] = None
            if window==self.selectedWindow:
                self.clearPointsTable()
        self.setSelectedPoints(None)
        self.markPointsStretchFactor = 1
        self.plotMarkedPoints(windows)
        
    def setSelectedPoints(self,points):
        self.selectedPoints = points
        if points is not None:
            self.markPointsTable.blockSignals(True)
            for row in range(self.markPointsTable.rowCount()):
                selected = True if row in self.selectedPoints else False
                for col in range(self.markPointsTable.columnCount()):
                    self.markPointsTable.item(row,col).setSelected(selected)
            self.markPointsTable.blockSignals(False)
        
    def deleteSelectedPoints(self):
        if len(self.selectedPoints)==len(self.markedPoints[self.selectedWindow]):
            self.clearMarkedPoints()
        else:
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            for window in windows:
                self.markedPoints[window] = np.delete(self.markedPoints[window],self.selectedPoints,0)
            for row in self.selectedPoints:
                self.markPointsTable.removeRow(row)
            self.setSelectedPoints(None)
            self.plotMarkedPoints(windows)
        
    def markPointsTableSelectionCallback(self):
        self.selectedPoints = None
        
    def setMarkedPointsLineStyle(self):
        sender = self.mainWin.sender()
        for option in (self.analysisMenuPointsLineNone,self.analysisMenuPointsLineLine,self.analysisMenuPointsLinePoly):
            option.setChecked(option is sender)
        self.plotMarkedPoints()
        
    def drawLines(self):
        sender = self.mainWin.sender()
        shapeIndex = self.imageShapeIndex[self.selectedWindow]
        axis = shapeIndex[2]
        rng = self.imageRange[self.selectedWindow][axis] if self.sliceProjState[self.selectedWindow] else [self.imageIndex[self.selectedWindow][axis]]*2
        ind = self.markedPoints[self.selectedWindow][:,axis].round()
        rows = np.logical_and(ind>=rng[0],ind<=rng[1])
        if not any(rows):
            return
        image = self.getImage()
        pts = self.markedPoints[self.selectedWindow][rows][:,shapeIndex[1::-1]]
        color = tuple(self.levelsMax[self.selectedWindow]*c for c in self.markPointsColor)
        if sender is self.analysisMenuPointsDrawTri:
            h,w = (self.imageShape[self.selectedWindow][i] for i in shapeIndex[:2])
            boundaryPts = getDelauneyBoundaryPoints(w,h)
            pts = np.concatenate((pts,boundaryPts),axis=0).astype(np.float32)
            triangles = getDelauneyTriangles(pts,w,h)
            for tri in triangles:
                p = [(tri[j],tri[j+1])for j in (0,2,4)]
                cv2.line(image,p[0],p[1],color,1,cv2.LINE_AA)
                cv2.line(image,p[1],p[2],color,1,cv2.LINE_AA)
                cv2.line(image,p[2],p[0],color,1,cv2.LINE_AA)
        else:
            if sender is self.analysisMenuPointsDrawPoly:
                pts = np.concatenate((pts,pts[-1]),axis=0)
            for p in pts:
                cv2.line(image,p[0],p[1],color,1,cv2.LINE_AA)
        self.imageItem[self.selectedWindow].setImage(image.transpose((1,0,2)),levels=[0,self.levelsMax[self.selectedWindow]])
        
    def copyPoints(self):
        if self.markedPoints[self.selectedWindow] is None:
            return
        sender = self.mainWin.sender()
        axis = self.imageShapeIndex[self.selectedWindow][2]
        ind = self.imageIndex[self.selectedWindow][axis]
        if sender==self.analysisMenuPointsCopyPrevious:
            ind -= 1
        elif sender==self.analysisMenuPointsCopyNext:
            ind += 1
        rows = self.markedPoints[self.selectedWindow][:,axis].round()==ind
        if not any(rows):
            return
        pts = self.markedPoints[self.selectedWindow][rows].copy()
        if sender==self.analysisMenuPointsCopyFlip:
            axis = self.imageShapeIndex[self.selectedWindow][1]
            pts[:,axis] = np.absolute(self.imageShape[self.selectedWindow][axis]-1-pts[:,axis])
        else:
            pts[:,axis] = self.imageIndex[self.selectedWindow][axis]
        self.markedPoints[self.selectedWindow] = np.concatenate((self.markedPoints[self.selectedWindow],pts))
        self.fillPointsTable(append=True)
        self.plotMarkedPoints([self.selectedWindow])
        
    def loadPoints(self):
        filePath,fileType = QtWidgets.QFileDialog.getOpenFileName(self.mainWin,'Choose saved points file',self.fileOpenPath,'*.npy')
        if filePath=='':
            return
        self.fileOpenPath = os.path.dirname(filePath)
        pts = np.load(filePath)[:,(1,0,2)]-1
        if self.markedPoints[self.selectedWindow] is not None:
            self.clearMarkedPoints()
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.markedPoints[window] = pts
            self.markPointsColorValues[window] = None
        self.markPointsStretchFactor = 1
        self.fillPointsTable()
        self.plotMarkedPoints()
        
    def savePoints(self):
        filePath,fileType = QtWidgets.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.npy')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        np.save(filePath,self.markedPoints[self.selectedWindow][:,(1,0,2)]+1)
        
    def clearPoints(self):
        self.clearMarkedPoints()
        
    def setPointsColorMap(self):
        colormap,ok = QtWidgets.QInputDialog.getItem(self.mainWin,'Set Color Map','Choose',('plasma','YlOrRd','jet'),editable=False)
        if not ok:
            return
        self.markPointsColorMap = colormap
        for window in self.displayedWindows:
            if self.markPointsColorValues[window] is not None:
                self.setPointColors(window)
                
    def setPointsColorThresh(self):
        thresh,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Set Color Threshold','threshold:',self.markPointsColorThresh[self.selectedWindow],min=0.01,max=1,decimals=2)
        if ok:
            self.markPointsColorThresh[self.selectedWindow] = thresh
            self.setPointColors(self.selectedWindow)
        
    def applyPointsColorMap(self):
        if self.markedPoints[self.selectedWindow] is None:
            return
        filePath,fileType = QtWidgets.QFileDialog.getOpenFileName(self.mainWin,'Choose file with values for each point',self.fileOpenPath,'*.npy')
        if filePath=='':
            return
        self.fileOpenPath = os.path.dirname(filePath)
        vals = np.load(filePath)
        self.markPointsColorThresh[self.selectedWindow] = 1
        if vals.size==self.markedPoints[self.selectedWindow].shape[0]:
            vals = vals.astype(float)
            vals -= vals.min()
            vals /= vals.max()
            self.markPointsColorValues[self.selectedWindow] = vals
            self.setPointColors(self.selectedWindow)
        else:
            self.markPointsColorValues[self.selectedWindow] = None
        
    def setPointColors(self,window):
        vals = self.markPointsColorValues[window]/self.markPointsColorThresh[window]
        vals[vals>1] = 1
        self.markPointsColorValuesRGB = getattr(matplotlib.cm,self.markPointsColorMap)(vals)[:,:3]
        self.plotMarkedPoints([window])
        
    def setPointsStretchFactor(self):
        stretch,ok = QtWidgets.QInputDialog.getDouble(self.mainWin,'Set Stretch Factor','stretch factor:',self.markPointsStretchFactor,min=0.00001,decimals=5)
        if not ok:
            return
        self.stretchPoints(stretch/self.markPointsStretchFactor)
        self.markPointsStretchFactor = stretch
    
    def stretchPoints(self,stretch):
        axes = self.imageShapeIndex[self.selectedWindow]
        imgInd = self.imageIndex[self.selectedWindow][axes[2]]
        rows = np.where(self.markedPoints[self.selectedWindow][:,axes[2]].round()==imgInd)[0]
        if rows.size>1:
            col = axes[0]
            y = self.markedPoints[self.selectedWindow][rows,col]
            y0 = y[-1]
            y -= y0
            y *= stretch
            y += y0
            self.markedPoints[self.selectedWindow][rows,col] = y
            for row in rows:
                ind = col if col==2 else int(not col)
                self.markPointsTable.item(row,ind).setText(str(self.markedPoints[self.selectedWindow][row,col]+1))
            self.plotMarkedPoints()
        
    def markPointsTableResizeCallback(self,event):
        w = int(self.markPointsTable.viewport().width()/3)
        for col in range(self.markPointsTable.columnCount()):
            self.markPointsTable.setColumnWidth(col,w)
        
    def markPointsTableKeyPressCallback(self,event):
        key = event.key()
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if key==QtCore.Qt.Key_C and int(modifiers & QtCore.Qt.ControlModifier)>0:
            selected = self.markPointsTable.selectedRanges()
            contents = ''
            pixelSize = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].pixelSize
            pixelSize = None if any(size is None for size in pixelSize) else [pixelSize[i] for i in (1,0,2)]
            for row in range(selected[0].topRow(),selected[0].bottomRow()+1):
                for col in range(selected[0].leftColumn(),selected[0].rightColumn()+1):
                    val = self.markPointsTable.item(row,col).text()
                    if int(modifiers & QtCore.Qt.AltModifier)>0 and pixelSize is not None:
                        val = str((float(val)-1)*pixelSize[col])
                    contents += val+'\t'
                contents = contents[:-1]+'\n'
            self.app.clipboard().setText(contents)
            
    def copyRefPoints(self):
        refWin = self.alignRefWindow[self.selectedWindow]
        if refWin is None or self.markedPoints[refWin] is None:
            return
        axis = self.alignAxis[self.selectedWindow]
        if self.mainWin.sender() is self.analysisMenuPointsCopyAlignedVol:
            self.markedPoints[self.selectedWindow] = None
            imgRange = self.imageRange[self.selectedWindow][axis]
        else:
            imgRange = (self.imageIndex[self.selectedWindow][axis],)*2
        for imgInd in range(imgRange[0],imgRange[1]+1):
            refInd = self.getAlignedRefImageIndex(self.selectedWindow,imgInd)
            pts = self.markedPoints[refWin][self.markedPoints[refWin][:,axis]==refInd].copy()
            pts[:,axis] = imgInd
            if self.markedPoints[self.selectedWindow] is None:
                self.markedPoints[self.selectedWindow] = pts
            else:
                rows = self.markedPoints[self.selectedWindow][:,axis].round()!=imgInd
                self.markedPoints[self.selectedWindow] = np.concatenate((self.markedPoints[self.selectedWindow][rows],pts))
        self.fillPointsTable()
        self.plotMarkedPoints()
        
    def alignCheckboxCallback(self):
        if self.alignCheckbox.isChecked():
            refWin = self.alignRefMenu.currentIndex()
            axis = self.imageShapeIndex[self.selectedWindow][2]
            start,end = self.alignRange[self.selectedWindow]
            reverse = False
            if start>end:
                start,end = end,start
                reverse = True
            n = end-start+1
            rng = self.imageRange[self.selectedWindow][axis]
            interval = n/(rng[1]-rng[0]+1)
            if start<0 or end>=self.imageShape[refWin][axis] or interval<1:
                self.alignCheckbox.setChecked(False)
                if interval<1:
                    raise Exception('Image range must be less than or equal to the reference alignment range')
                else:
                    raise Exception('Align start and end must be between 1 and the number of reference images')
            self.alignRefWindow[self.selectedWindow] = refWin
            self.alignAxis[self.selectedWindow] = axis
            alignInd = np.arange(n)/interval+rng[0]
            self.alignIndex[self.selectedWindow] = -np.ones(self.imageShape[refWin][axis],dtype=int)
            self.alignIndex[self.selectedWindow][start:end+1] = alignInd[::-1] if reverse else alignInd
            self.imageIndex[refWin][axis] = self.getAlignedRefImageIndex(self.selectedWindow,self.imageIndex[self.selectedWindow][axis])
            self.displayImage([refWin])
        else:
            self.alignRefWindow[self.selectedWindow] = None
            if self.imageIndex[self.selectedWindow][self.alignAxis[self.selectedWindow]]<0:
                self.imageIndex[self.selectedWindow][self.alignAxis[self.selectedWindow]] = 0
                self.displayImage([self.selectedWindow])
            
    def alignWindows(self,window,axis):
        if window in self.alignRefWindow:
            alignedWindow = self.alignRefWindow.index(window)
            if self.alignAxis[alignedWindow]==axis:
                self.imageIndex[alignedWindow][axis] = self.alignIndex[alignedWindow][self.imageIndex[window][axis]]
                self.displayImage([alignedWindow])
        elif self.alignRefWindow[window] is not None:
            if self.alignAxis[self.selectedWindow]==axis:
                self.imageIndex[self.alignRefWindow[window]][axis] = self.getAlignedRefImageIndex(window,self.imageIndex[window][axis])
                self.displayImage([self.alignRefWindow[window]])
                
    def getAlignedRefImageIndex(self,window,imageIndex):
        refInd = np.where(self.alignIndex[window]==imageIndex)[0]
        return refInd[0]+refInd.size//2
                
    def alignStartEditCallback(self):
        self.setAlignRange(self.alignStartEdit.text(),0)
        
    def alignEndEditCallback(self):
        self.setAlignRange(self.alignEndEdit.text(),1)
        
    def setAlignRange(self,val,ind):
        self.alignRange[self.selectedWindow][ind] = int(val)-1 if str(val).isdigit() else None
        
    def getContours(self):
        image = self.getImage(self.selectedWindow,downsample=self.displayDownsample[self.selectedWindow],binary=True)
        yRange,xRange = [[r//self.displayDownsample[self.selectedWindow] for r in self.imageRange[self.selectedWindow][axis]] for axis in self.imageShapeIndex[self.selectedWindow][:2]]
        roi = image[yRange[0]:yRange[1]+1,xRange[0]:xRange[1]+1]
        contours,_ = cv2.findContours(roi.max(axis=2),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        contours = [c for c in contours if c.shape[0]>=self.minContourVertices]
        for c in contours:
            c[:,0,:2] += [xRange[0],yRange[0]]
        if len(contours)>1 and (self.analysisMenuContoursMergeHorz.isChecked() or self.analysisMenuContoursMergeVert.isChecked()):
            mergeAxis = 1 if self.analysisMenuContoursMergeHorz.isChecked() else 0
            contours.sort(key=lambda x: x[:,0,mergeAxis].min())
            mergedContours = [contours[0]]
            for c in contours[1:]:
                merged = False
                for i,m in enumerate(mergedContours):
                    if np.any(np.in1d(c[:,0,mergeAxis],m[:,0,mergeAxis])):
                        mergedContours[i] = np.concatenate((m,c),axis=0)
                        merged = True
                        break
                if not merged:
                    mergedContours.append(c)
        else:
            mergedContours = contours
        self.contourHulls = []
        self.contourRectangles = []
        for m in mergedContours:
            self.contourHulls.append(cv2.convexHull(m))
            x,y,w,h = cv2.boundingRect(m)
            self.contourRectangles.append([x-1,y-1,w+2,h+2])
        color = tuple(255*c for c in self.contourLineColor)
        lineWidth = -1 if self.analysisMenuContoursFill.isChecked() else 1
        sender = self.mainWin.sender()
        if sender is self.analysisMenuContoursFindRectangle:
            for r in self.contourRectangles:
                cv2.rectangle(image,(r[0],r[1]),(r[0]+r[2],r[1]+r[3]),color,lineWidth,cv2.LINE_AA)
        else:
            c = mergedContours if sender is self.analysisMenuContoursFindContours else self.contourHulls
            cv2.drawContours(image,c,-1,color,lineWidth,cv2.LINE_AA)
        self.imageItem[self.selectedWindow].setImage(image.transpose((1,0,2)),levels=[0,255])
        
    def setMinContourVertices(self):
        n,ok = QtWidgets.QInputDialog.getInt(self.mainWin,'Select','Minimum number of contour vertices',self.minContourVertices,min=1)
        if ok:
            self.minContourVertices = n
            
    def setMergeContours(self):
        sender = self.mainWin.sender()
        if sender.isChecked():
            if sender is self.analysisMenuContoursMergeHorz:
                self.analysisMenuContoursMergeVert.setChecked(False)
            else:
                self.analysisMenuContoursMergeHorz.setChecked(False)
    
    def saveContours(self):
        filePath,fileType = QtWidgets.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'Image (*.tif *.png *.jpg)')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        image = self.getImage()
        for ind,r in enumerate(self.contourRectangles):
            r = [max(0,i*self.displayDownsample[self.selectedWindow]) for i in r]
            fileName,fileExt = os.path.splitext(filePath)
            cv2.imwrite(fileName+'_'+str(ind+1)+fileExt,image[r[1]:r[1]+r[3],r[0]:r[0]+r[2],::-1])


class ImageObj():
    
    def __init__(self,filePath,fileType,chFileOrg,numCh,loadData,memmap,autoColor):
        self.data = None
        self.memmap = memmap
        self.alpha = 1
        self.alphaMap = None
        self.pixelSize = [None]*3
        self.position = None
        if isinstance(filePath,np.ndarray):
            self.fileType = 'data'
            self.filePath = None
            self.data = filePath
            self.dtype = np.uint16 if self.data.dtype==np.uint16 else np.uint8
            shape = self.data.shape
            numImg = shape[2] if len(shape)>2 else 1
            numCh = shape[3] if len(shape)>3 else 1
            if numCh==4:
                numCh = 3
            self.shape = shape[:2]+(numImg,numCh)
        elif fileType=='Image Data (*.tif *.btf *.png *.jpg *.jp2 *.npy *.npz *.nrrd *.nii)':
            fileExt = os.path.splitext(filePath)[1][1:]
            if fileExt in ('npy','npz'):
                self.fileType = 'numpy'
                self.filePath = filePath
                if fileExt=='npz':
                    z = zipfile.ZipFile(filePath)
                    npy = z.open(z.namelist()[0])
                else:
                    npy = open(filePath,'rb')
                version = np.lib.format.read_magic(npy)
                shape,fortran,dtype = np.lib.format._read_array_header(npy,version)
                npy.close()
                self.dtype = dtype if dtype==np.uint16 else np.uint8
                numImg = shape[2] if len(shape)>2 else 1
                numCh = shape[3] if len(shape)>3 else 1
                if numCh==4:
                    numCh = 3
                self.shape = shape[:2]+(numImg,numCh)
            elif fileExt in ('nrrd','nii'):
                self.fileType = fileExt
                self.filePath = filePath
                self.dtype = np.uint8
                self.shape = (320,456,528,1)
                self.pixelSize = [25.0]*3
            else:
                self.fileType = 'bigtiff' if fileExt=='btf' else 'image'
                self.dtype,shape,numCh = getImageInfo(filePath)
                self.filePath = [[filePath]]*numCh
                self.shape = shape+(1,numCh)  
        elif fileType=='Image Series (*.tif *.btf *.png *.jpg *.jp2)':
            for ind,f in enumerate(filePath):
                fext = os.path.splitext(f)[1][1:]
                dtype,s,n = getImageInfo(f)
                if ind==0:
                    if numCh is None:
                        numCh = n
                    self.fileType = 'bigtiff' if fext=='btf' else 'image'
                    self.filePath = [[] for _ in range(numCh)]
                    self.dtype = dtype
                    shape = s
                else:
                    if (self.fileType=='bitfiff' and fext!='btf') or (self.fileType=='image' and fext=='btf'):
                        raise Exception('All image files in series must be .btf if any are .btf')
                    if dtype!=self.dtype:
                        raise Exception('All images in series must have the same data type')
                    if chFileOrg=='rgb':
                        if n!=numCh:
                            raise Exception('All rgb images must have the same number of channels')
                    elif n>1:
                        raise Exception('Images must be grayscale if channel file organization is not rgb')
                    shape = (max(shape[0],s[0]),max(shape[1],s[1]))
                if chFileOrg=='rgb':
                    for ch in range(numCh):
                        self.filePath[ch].append(f)
                else:
                    ch = ind%numCh if chFileOrg=='alternating' else ind//int(len(filePath)/numCh)
                    self.filePath[ch].append(f)
            numImg = len(filePath) if chFileOrg=='rgb' else int(len(filePath)/numCh)
            self.shape = shape+(numImg,numCh)
        elif fileType in ('Bruker Dir (*.xml)','Bruker Dir + Siblings (*.xml)'):
            self.fileType = 'image'
            xml = minidom.parse(filePath)
            pvStateValues = xml.getElementsByTagName('PVStateValue')
            linesPerFrame = int(pvStateValues[7].getAttribute('value'))
            pixelsPerLine = int(pvStateValues[15].getAttribute('value'))
            frames = xml.getElementsByTagName('Frame')
            numImg = len(frames)
            numCh = len(frames[0].getElementsByTagName('File'))
            self.filePath = [[] for _ in range(numCh)]
            self.dtype = np.uint16
            self.shape = (linesPerFrame,pixelsPerLine,numImg,numCh)
            zpos = []
            for frame in frames:
                zpos.append(float(frame.getElementsByTagName('SubindexedValue')[2].getAttribute('value')))
                for ch,tifFile in enumerate(frame.getElementsByTagName('File')):
                    f = os.path.join(os.path.dirname(filePath),tifFile.getAttribute('filename'))
                    self.filePath[ch].append(f)
            self.pixelSize = [round(float(pvStateValues[9].getElementsByTagName('IndexedValue')[0].getAttribute('value')),4)]*2
            if len(frames)>1:
                self.pixelSize.append(round(zpos[1]-zpos[0],4))
            else:
                self.pixelSize.append(None)
            xpos = float(pvStateValues[17].getElementsByTagName('SubindexedValue')[0].getAttribute('value'))
            ypos = float(pvStateValues[17].getElementsByTagName('SubindexedValue')[1].getAttribute('value'))
            self.position = [int(ypos/self.pixelSize[0]),int(xpos/self.pixelSize[1]),int(zpos[0]/self.pixelSize[2])]
        self.bitDepth = 16 if self.dtype==np.uint16 else 8
        self.levels = [[0,2**self.bitDepth-1] for _ in range(self.shape[3])]
        self.gamma = [1]*self.shape[3]
        self.rgbInd = [(0,1,2) for _ in range(self.shape[3])]
        if autoColor:
            for ch in range(self.shape[3])[:3]:
                self.rgbInd[ch] = (ch,)
        if self.data is None:
            if loadData:
                self.data = self.getData()
        else:
            self.data = self.formatData(self.data)
            
    def getOffsets(self):
        offset = np.zeros((self.shape[2],2),dtype=int)
        for img in range(self.shape[2]):
            imgShape = getImageInfo(self.filePath[0][img])[1]
            offset[img] = [(self.shape[n]-imgShape[n])//2 for n in (0,1)]
        return offset
            
    def getData(self,channels=None,rangeSlice=None):
        # returns array with shape height x width x n x channels
        if channels is None:
            channels = list(range(self.shape[3]))
        if rangeSlice is None:
            rangeSlice = slice(0,self.shape[2])
        if self.data is None:
            if self.fileType in ('image','bigtiff'):
                imgInd = range(rangeSlice.start,rangeSlice.stop)
                data = np.zeros(self.shape[:2]+(len(imgInd),len(channels)),dtype=self.dtype)
                for ind,img in enumerate(imgInd):
                    for c,ch in enumerate(channels):
                        d = getImageData(self.filePath[ch][img],self.memmap)
                        i = (self.shape[0]-d.shape[0])//2
                        j = (self.shape[1]-d.shape[1])//2
                        if len(d.shape)>2:
                            data[i:i+d.shape[0],j:j+d.shape[1],ind,:] = d[:,:,channels]
                            break
                        else:
                            data[i:i+d.shape[0],j:j+d.shape[1],ind,c] = d
                return data
            elif self.fileType=='numpy':
                d = np.load(self.filePath)
                if isinstance(d,np.lib.npyio.NpzFile):
                    d = d[list(d.keys())[0]]
                data = self.formatData(d)
            elif self.fileType=='nrrd':
                data,_ = nrrd.read(self.filePath)
                data = self.formatData(data.transpose((1,2,0)))
            elif self.fileType=='nii':
                d = nibabel.nifti1.load(self.filePath)
                data = d.get_data()
                data = self.formatData(data.transpose((1,2,0)))
        else:
            data = self.data
        return data[:,:,rangeSlice,channels]
        
    def getDataIterator(self,channels=None,rangeSlice=None):
        if channels is None:
            channels = list(range(self.shape[3]))
        if rangeSlice is None:
            rangeSlice = slice(0,self.shape[2])
        if self.data is None:
            data = None if self.fileType in ('image','bigtiff') else self.getData(channels,rangeSlice)
        else:
            data = self.data
        for img in range(rangeSlice.start,rangeSlice.stop):
            for ch in channels:
                if data is None:
                    imgData = getImageData(self.filePath[ch][img],self.memmap)
                    if len(imgData.shape)<3:
                        numCh = 1
                        dshape = self.shape[:2]
                    else:
                        numCh = imgData.shape[2]
                        dshape = self.shape[:2]+(numCh,)
                    d = np.zeros(dshape,dtype=self.dtype)
                    i = (self.shape[0]-imgData.shape[0])//2
                    j = (self.shape[1]-imgData.shape[1])//2
                    d[i:i+imgData.shape[0],j:j+imgData.shape[1]] = imgData
                    if numCh>1:
                        for c in channels:
                            yield d[:,:,c]
                        break
                    else:
                        yield d
                else:
                    yield data[:,:,img,ch]
        
    def formatData(self,data):
        if data.dtype!=self.dtype:
            data = data.astype(float)
            data *= (2**self.bitDepth-1)/np.nanmax(data)
            data.round(out=data)
            data = data.astype(self.dtype)
        if len(data.shape)<3:
            data = data[:,:,None,None]
        elif len(data.shape)<4:
            data = data[:,:,:,None]
        if data.shape[3]==4 and self.shape[3]==3:
            self.alphaMap = data[:,:,:,3]
            data = data[:,:,:,:3]
        return data
        
    def convertDataType(self):
        if self.dtype==np.uint8:
            dtype = np.uint16
            bitDepth = 16
        else:
            dtype = np.uint8
            bitDepth = 8
        scaleFactor = (2**bitDepth-1)/(2**self.bitDepth-1)
        self.data = self.data.astype(float)
        self.data *= scaleFactor
        self.data.round(out=self.data)
        self.data = self.data.astype(dtype)
        self.dtype = dtype
        self.bitDepth = bitDepth
        self.levels = [[int(round(level*scaleFactor)) for level in levels] for levels in self.levels]
        
    def invert(self):
        if self.data is None:
            pass
        else:
            levelsMax = 2**self.bitDepth-1
            self.data = levelsMax - self.data
            self.levels = [[levelsMax-level for level in reversed(levels)] for levels in self.levels]
            
    def normalize(self,option):
        if self.data is None:
            pass
        else:
            data = self.data.astype(float)
            if option=='images':
                for i in range(data.shape[2]):
                    for ch in range(data.shape[3]):
                        dmin = self.data[:,:,i,ch].min()
                        dmax = self.data[:,:,i,ch].max()
                        data[:,:,i,ch] -= dmin 
                        data[:,:,i,ch] /= (dmax-dmin)/(2**self.bitDepth-1)
            else:
                for ch in range(data.shape[3]):
                    dmin = self.data[:,:,:,ch].min()
                    dmax = self.data[:,:,:,ch].max()
                    data[:,:,:,ch] -= dmin 
                    data[:,:,:,ch] /= (dmax-dmin)/(2**self.bitDepth-1)
            self.data = data.astype(self.dtype)
            self.levels = [[0,2**self.bitDepth-1] for _ in range(self.shape[3])]
            
    def changeBackground(self,option,thresh):
        if self.data is None:
            pass
        else:
            maxLevel = 2**self.bitDepth-1
            if option=='b2w':
                self.data[np.all(self.data<=maxLevel*thresh,axis=3)] = maxLevel
            else:
                self.data[np.all(self.data>=maxLevel*(1-thresh),axis=3)] = 0
        
    def flip(self,axis,imgAxis=None,imgInd=None):
        if self.data is None:
            if imgInd is None and axis==2:
                for chFiles in self.filePath:
                    chFiles.reverse()
        else:
            ind = [slice(None)]*3
            if imgInd is not None:
                ind[imgAxis] = slice(imgInd,imgInd+1)
            flipInd = ind[:]
            flipInd[axis] = slice(None,None,-1)
            self.data[ind] = self.data[flipInd]
        
    def rotate90(self,direction,axes):
        if self.data is None:
            pass
        else:
            self.data = np.rot90(self.data,direction,axes)
            self.shape = self.data.shape
            
    def rotate(self,angle,axes):
        if self.data is None:
            pass
        else:
            self.data = scipy.ndimage.interpolation.rotate(self.data,angle,axes)
            self.shape = self.data.shape


def getImageInfo(filePath):
    fileExt = os.path.splitext(filePath)[1][1:]
    if fileExt in ('tif','btf'):
        img = tifffile.TiffFile(filePath)
        dtype = np.uint16 if img.pages[0].bitspersample==16 else np.uint8
        shape = img.pages[0].shape
        if len(shape)>2:
            numCh = shape[2]
            shape = shape[:2]
        else:
            # numCh = len(img.pages)
            numCh = sum(1 for p in img.pages if p.shape==shape)
        img.close()
    elif fileExt=='png':
        img = png.Reader(str(filePath)).read()
        dtype = np.uint16 if img[3]['bitdepth']==16 else np.uint8
        shape = img[1::-1]
        numCh = img[3]['planes']
    else:
        img = PIL.Image.open(filePath)
        if hasattr(img,'bits'):
            dtype = np.uint16 if img.bits==16 else np.uint8
        elif img.mode=='I;16':
            dtype = np.uint16
        else:
            dtype = np.uint16 if cv2.imread(filePath,cv2.IMREAD_UNCHANGED).dtype==np.uint16 else np.uint8
        shape = img.size[::-1]
        numCh = 3 if img.mode=='RGB' else 1
        img.close()
    return dtype,shape,numCh

def getImageData(filePath,memmap=False):
    fileExt = os.path.splitext(filePath)[1][1:]
    if fileExt in ('tif','btf'):
        img = tifffile.TiffFile(filePath)
        out = 'memmap' if memmap else None
        data = img.asarray(out=out)
        if len(img.pages)>1 and len(data.shape)>2:
            data = data.transpose((1,2,0))[:,:,::-1]
        img.close()
    else:
        data = cv2.imread(filePath,cv2.IMREAD_UNCHANGED)
        if len(data.shape)>2:
            data = data[:,:,::-1]
    return data
    
def applyLUT(data,levels,binary=False,gamma=1):
    dtype,maxVal = (np.uint8,2**8-1) if binary or data.dtype==np.uint8 else (np.uint16,2**16-1)
    if binary:
        levels = [levels[1]-1,levels]
    lut = np.arange(maxVal+1)
    lut.clip(levels[0],levels[1],out=lut)
    lut -= levels[0]
    lut /= (levels[1]-levels[0])/maxVal
    if gamma!=1 and not binary:
        lut /= maxVal
        lut **= gamma
        lut *= maxVal
    return np.take(lut.astype(dtype),data)
    
def getDelauneyBoundaryPoints(w,h):
    return [(0,0),(w/2,0),(w-1,0),(w-1,h/2),(w-1,h-1),(w/2,h-1),(0,h-1),(0,h/2)]
    
def getDelauneyTriangles(pts,w,h):
    subdiv = cv2.Subdiv2D((0,0,w,h))
    for p in pts:
        subdiv.insert((p[0],p[1]))
    triangles = subdiv.getTriangleList()
    return triangles[np.all(triangles>=0,axis=1) & np.all(triangles[:,::2]<w,axis=1) & np.all(triangles[:,1::2]<h,axis=1)]

def setLayoutGridSpacing(layout,height,width,rows,cols):
    for row in range(rows):
        layout.setRowMinimumHeight(row,height/rows)
        layout.setRowStretch(row,1)
    for col in range(cols):
        layout.setColumnMinimumWidth(col,width/cols)
        layout.setColumnStretch(col,1)        

def getSelectedItemsIndex(listbox):
    selectedItemsIndex = []
    for i in range(listbox.count()):
        if listbox.item(i).isSelected():
            selectedItemsIndex.append(i)
    return selectedItemsIndex


if __name__=="__main__":
    start()