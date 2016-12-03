# -*- coding: utf-8 -*-
"""
image viewer GUI

@author: samgale
"""

from __future__ import division
import sip
sip.setapi('QString', 2)
import copy, os, math, pickle, cv2, nrrd
from xml.dom import minidom
import numpy as np
from PyQt4 import QtGui, QtCore
import pyqtgraph as pg


def start():
    app = QtGui.QApplication.instance()
    if app is None:
        app = QtGui.QApplication([])
    w = ImageGUI(app)
    app.exec_()


class ImageGUI():
    
    def __init__(self,app):
        self.app = app
        self.fileOpenPath = os.path.dirname(os.path.realpath(__file__))
        self.fileOpenType = 'Images (*.tif *.jpg)'
        self.fileSavePath = copy.copy(self.fileOpenPath)
        self.imageObjs = []
        
        # main window
        winHeight = 500
        winWidth = 1000
        self.mainWin = QtGui.QMainWindow()
        self.mainWin.setWindowTitle('ImageGUI')
        self.mainWin.keyPressEvent = self.mainWinKeyPressCallback
        self.mainWin.resizeEvent = self.mainWinResizeCallback
        self.mainWin.closeEvent = self.mainWinCloseCallback
        self.mainWin.resize(winWidth,winHeight)
        screenCenter = QtGui.QDesktopWidget().availableGeometry().center()
        mainWinRect = self.mainWin.frameGeometry()
        mainWinRect.moveCenter(screenCenter)
        self.mainWin.move(mainWinRect.topLeft())
        
        # file menu
        self.menuBar = self.mainWin.menuBar()
        self.menuBar.setNativeMenuBar(False)
        self.fileMenu = self.menuBar.addMenu('File')        
        self.fileMenuOpen = QtGui.QAction('Open',self.mainWin)
        self.fileMenuOpen.triggered.connect(self.openFile)
        self.fileMenu.addAction(self.fileMenuOpen)
        
        self.fileMenuSave = self.fileMenu.addMenu('Save')
        self.fileMenuSaveImage = QtGui.QAction('Image',self.mainWin)
        self.fileMenuSaveImage.triggered.connect(self.saveImage)
        self.fileMenuSaveVolume = QtGui.QAction('Volume',self.mainWin)
        self.fileMenuSaveVolume.triggered.connect(self.saveVolume)
        self.fileMenuSave.addActions([self.fileMenuSaveImage,self.fileMenuSaveVolume])
        
        # image menu
        self.imageMenu = self.menuBar.addMenu('Image')
        self.imageMenuFlip = self.imageMenu.addMenu('Flip')
        self.imageMenuFlipHorz = QtGui.QAction('Horizontal',self.mainWin)
        self.imageMenuFlipHorz.triggered.connect(self.flipImageHorz)
        self.imageMenuFlipVert = QtGui.QAction('Vertical',self.mainWin)
        self.imageMenuFlipVert.triggered.connect(self.flipImageVert)
        self.imageMenuFlip.addActions([self.imageMenuFlipHorz,self.imageMenuFlipVert])
        
        self.imageMenuRange = self.imageMenu.addMenu('Range')
        self.imageMenuRangeLoad = QtGui.QAction('Load',self.mainWin)
        self.imageMenuRangeLoad.triggered.connect(self.loadRange)
        self.imageMenuRangeSave = QtGui.QAction('Save',self.mainWin)
        self.imageMenuRangeSave.triggered.connect(self.saveRange)
        self.imageMenuRange.addActions([self.imageMenuRangeLoad,self.imageMenuRangeSave])
        
        # tools menu
        self.toolsMenu = self.menuBar.addMenu('Tools')
        self.toolsMenuPixelSize = self.toolsMenu.addMenu('Set Pixel Size')
        self.toolsMenuPixelSizeXY = QtGui.QAction('XY',self.mainWin)
        self.toolsMenuPixelSizeXY.triggered.connect(self.setPixelSize)
        self.toolsMenuPixelSizeZ = QtGui.QAction('Z',self.mainWin)
        self.toolsMenuPixelSizeZ.triggered.connect(self.setPixelSize)
        self.toolsMenuPixelSize.addActions([self.toolsMenuPixelSizeXY,self.toolsMenuPixelSizeZ])
        
        self.toolsMenuSetRelThresh = QtGui.QAction('Set Relative Intensity Threshold',self.mainWin)
        self.toolsMenuSetRelThresh.triggered.connect(self.setRelativeIntensityThresh)
        self.relativeIntensityThresh = 0.2
        self.toolsMenuSetAbsThresh = QtGui.QAction('Set Absolute Intensity Threshold',self.mainWin)
        self.toolsMenuSetAbsThresh.triggered.connect(self.setAbsIntensityThresh)
        self.absIntensityThresh = 2
        self.toolsMenu.addActions([self.toolsMenuSetRelThresh,self.toolsMenuSetAbsThresh])
        
        self.toolsMenuMeasure = self.toolsMenu.addMenu('Measure')
        self.toolsMenuMeasureLength = QtGui.QAction('Length',self.mainWin)
        self.toolsMenuMeasureArea = QtGui.QAction('Area',self.mainWin)
        self.toolsMenuMeasureOverlap = QtGui.QAction('Overlap',self.mainWin)
        self.toolsMenuMeasureOverlap.triggered.connect(self.measureOverlap)
        self.toolsMenuMeasure.addActions([self.toolsMenuMeasureLength,self.toolsMenuMeasureArea,self.toolsMenuMeasureOverlap])
        
        self.toolsMenuContour = self.toolsMenu.addMenu('Contour')
        self.toolsMenuContourFind = QtGui.QAction('Find',self.mainWin)
        self.toolsMenuContourFind.triggered.connect(self.findContour)
        self.toolsMenuContourLoad = QtGui.QAction('Load',self.mainWin)
        self.toolsMenuContourLoad.triggered.connect(self.loadContour)
        self.toolsMenuContourSave = QtGui.QAction('Save',self.mainWin)
        self.toolsMenuContourSave.triggered.connect(self.saveContour)
        self.toolsMenuContourAutoSave = QtGui.QAction('Auto Save',self.mainWin,checkable=True)
        self.toolsMenuContour.addActions([self.toolsMenuContourFind,self.toolsMenuContourLoad,self.toolsMenuContourSave,self.toolsMenuContourAutoSave])
        
        self.toolsMenuFindInRegion = QtGui.QAction('Find Data In Region',self.mainWin)
        self.toolsMenu.addAction(self.toolsMenuFindInRegion)
        self.toolsMenuFindInRegion.triggered.connect(self.findInRegion)
        
        self.toolsMenuAtlas = self.toolsMenu.addMenu('Allen Atlas')
        self.toolsMenuAtlasRegions = self.toolsMenuAtlas.addMenu('Select Regions')
        self.atlasAnnotationData = None
        self.atlasRegionLabels = ('LGd','LGv','LP','LD','VISp','VISpl','VISpm','VISli','VISpor')
        self.atlasRegionIDs = (170,178,218,155,(593,821,721,778,33,305),(750,269,869,902,377,393),(805,41,501,565,257,469),(312782578,312782582,312782586,312782590,312782594,312782598),(312782632,312782636,312782640,312782644,312782648,312782652))
        self.selectedAtlasRegions = []
        self.atlasRegionsMenu = []
        for region in self.atlasRegionLabels:
            self.atlasRegionsMenu.append(QtGui.QAction(region,self.mainWin,checkable=True))
            self.atlasRegionsMenu[-1].triggered.connect(self.setAtlasRegions)
        self.toolsMenuAtlasRegions.addActions(self.atlasRegionsMenu)
        self.toolsMenuAtlasClear = QtGui.QAction('Clear All',self.mainWin)
        self.toolsMenuAtlasClear.triggered.connect(self.clearAtlasRegions)
        self.toolsMenuAtlas.addAction(self.toolsMenuAtlasClear)
        
        # image window
        self.imageLayout = pg.GraphicsLayoutWidget()
        self.imageViewBox = self.imageLayout.addViewBox(invertY=True,enableMouse=False,enableMenu=False)
        self.imageItem = pg.ImageItem()
        self.imageViewBox.sigRangeChanged.connect(self.imageRangeChanged)
        self.ignoreImageRangeChange = False
        self.imageViewBox.addItem(self.imageItem)
        
        # file info
        self.fileListbox = QtGui.QListWidget()
        self.fileListbox.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.fileListbox.itemSelectionChanged.connect(self.fileListboxSelectionCallback)
        self.fileListbox.itemClicked.connect(self.fileListboxItemClickedCallback)
        
        self.stitchCheckbox = QtGui.QCheckBox('Stitch')
        self.stitchCheckbox.stateChanged.connect(self.stitchCheckboxCallback) 
        
        self.moveFileDownButton = QtGui.QPushButton('Down')
        self.moveFileDownButton.clicked.connect(self.moveFileDownButtonCallback)
        
        self.moveFileUpButton = QtGui.QPushButton('Up')
        self.moveFileUpButton.clicked.connect(self.moveFileUpButtonCallback)
        
        self.removeFileButton = QtGui.QPushButton('Remove')
        self.removeFileButton.clicked.connect(self.removeFileButtonCallback)
        
        self.channelListbox = QtGui.QListWidget()
        self.channelListbox.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.channelListbox.itemSelectionChanged.connect(self.channelListboxCallback)
        
        self.channelColorMenu = QtGui.QComboBox()
        self.channelColorMenu.addItems(('Color','Gray','Red','Green','Blue','Magenta'))
        self.channelColorMenu.currentIndexChanged.connect(self.channelColorMenuCallback)
        
        self.imageDimensionsLabel = QtGui.QLabel('XYZ Dimensions: ')
        self.imagePixelSizeLabel = QtGui.QLabel('XYZ Pixel Size (\u03BCm): ')
        
        self.fileInfoLayout = QtGui.QGridLayout() 
        self.fileInfoLayout.addWidget(self.stitchCheckbox,0,1,1,2,alignment=QtCore.Qt.AlignHCenter)
        self.fileInfoLayout.addWidget(self.channelListbox,1,0,3,2)
        self.fileInfoLayout.addWidget(self.moveFileDownButton,1,2,1,1)
        self.fileInfoLayout.addWidget(self.moveFileUpButton,1,3,1,1)
        self.fileInfoLayout.addWidget(self.removeFileButton,2,2,1,2)
        self.fileInfoLayout.addWidget(self.channelColorMenu,3,2,1,2)
        self.fileInfoLayout.addWidget(self.imageDimensionsLabel,4,0,1,4)
        self.fileInfoLayout.addWidget(self.imagePixelSizeLabel,5,0,1,4)
        
        # view control
        self.imageNumEditLayout = QtGui.QFormLayout()
        self.imageNumEdit = QtGui.QLineEdit('')
        self.imageNumEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.imageNumEdit.editingFinished.connect(self.imageNumEditCallback)
        self.imageNumEditLayout.addRow('Image #:',self.imageNumEdit)
        
        self.sliceProjGroupBox = QtGui.QGroupBox()
        self.sliceProjGroupLayout = QtGui.QVBoxLayout()
        self.sliceButton = QtGui.QRadioButton('Slice')
        self.sliceButton.setChecked(True)
        self.sliceButton.clicked.connect(self.sliceProjButtonCallback)
        self.projectionButton = QtGui.QRadioButton('Projection')
        self.projectionButton.clicked.connect(self.sliceProjButtonCallback)
        self.sliceProjGroupLayout.addWidget(self.sliceButton)
        self.sliceProjGroupLayout.addWidget(self.projectionButton)
        self.sliceProjGroupBox.setLayout(self.sliceProjGroupLayout)
        
        self.xyzGroupBox = QtGui.QGroupBox()
        self.xyzGroupLayout = QtGui.QVBoxLayout()
        self.xButton = QtGui.QRadioButton('X')
        self.xButton.clicked.connect(self.xyzButtonCallback)
        self.yButton = QtGui.QRadioButton('Y')
        self.yButton.clicked.connect(self.xyzButtonCallback)
        self.zButton = QtGui.QRadioButton('Z')
        self.zButton.setChecked(True)
        self.zButton.clicked.connect(self.xyzButtonCallback)
        self.xyzGroupLayout.addWidget(self.xButton)
        self.xyzGroupLayout.addWidget(self.yButton)
        self.xyzGroupLayout.addWidget(self.zButton)
        self.xyzGroupBox.setLayout(self.xyzGroupLayout)
        self.imageShapeIndex = (0,1,2)
        
        self.viewControlLayout = QtGui.QGridLayout()
        self.viewControlLayout.addLayout(self.imageNumEditLayout,0,0,1,1)
        self.viewControlLayout.addWidget(self.sliceProjGroupBox,1,0,2,1)
        self.viewControlLayout.addWidget(self.xyzGroupBox,0,1,3,1)
        
        # range control 
        self.zoomPanButton = QtGui.QPushButton('Zoom/Pan',checkable=True)
        self.zoomPanButton.clicked.connect(self.zoomPanButtonCallback)        
        
        self.resetViewButton = QtGui.QPushButton('Reset View')
        self.resetViewButton.clicked.connect(self.resetViewButtonCallback)
        
        self.xRangeLayout = QtGui.QHBoxLayout()
        self.xRangeLabel = QtGui.QLabel('X Range')
        self.xRangeLowEdit = QtGui.QLineEdit('')
        self.xRangeLowEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.xRangeLowEdit.editingFinished.connect(self.xRangeLowEditCallback)
        self.xRangeHighEdit = QtGui.QLineEdit('')
        self.xRangeHighEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.xRangeHighEdit.editingFinished.connect(self.xRangeHighEditCallback)
        self.xRangeLayout.addWidget(self.xRangeLabel)
        self.xRangeLayout.addWidget(self.xRangeLowEdit)
        self.xRangeLayout.addWidget(self.xRangeHighEdit)
        
        self.yRangeLayout = QtGui.QHBoxLayout()
        self.yRangeLabel = QtGui.QLabel('Y Range')
        self.yRangeLowEdit = QtGui.QLineEdit('')
        self.yRangeLowEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.yRangeLowEdit.editingFinished.connect(self.yRangeLowEditCallback)
        self.yRangeHighEdit = QtGui.QLineEdit('')
        self.yRangeHighEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.yRangeHighEdit.editingFinished.connect(self.yRangeHighEditCallback)
        self.yRangeLayout.addWidget(self.yRangeLabel)
        self.yRangeLayout.addWidget(self.yRangeLowEdit)
        self.yRangeLayout.addWidget(self.yRangeHighEdit)
        
        self.zRangeLayout = QtGui.QHBoxLayout()
        self.zRangeLabel = QtGui.QLabel('Z Range')
        self.zRangeLowEdit = QtGui.QLineEdit('')
        self.zRangeLowEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.zRangeLowEdit.editingFinished.connect(self.zRangeLowEditCallback)
        self.zRangeHighEdit = QtGui.QLineEdit('')
        self.zRangeHighEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.zRangeHighEdit.editingFinished.connect(self.zRangeHighEditCallback)
        self.zRangeLayout.addWidget(self.zRangeLabel)
        self.zRangeLayout.addWidget(self.zRangeLowEdit)
        self.zRangeLayout.addWidget(self.zRangeHighEdit)
        
        self.rangeControlLayout = QtGui.QGridLayout()
        self.rangeControlLayout.addWidget(self.zoomPanButton,0,0,1,1)
        self.rangeControlLayout.addWidget(self.resetViewButton,0,1,1,1)
        self.rangeControlLayout.addLayout(self.xRangeLayout,1,0,1,2)
        self.rangeControlLayout.addLayout(self.yRangeLayout,2,0,1,2)
        self.rangeControlLayout.addLayout(self.zRangeLayout,3,0,1,2)
                
        # levels control
        self.levelsPlotWidget = pg.PlotWidget(enableMenu=False)
        self.levelsPlotItem = self.levelsPlotWidget.getPlotItem()
        self.levelsPlotItem.setMouseEnabled(x=False,y=False)
        self.levelsPlotItem.hideButtons()
        self.levelsPlotItem.setLabel('left','log(# Pixels)')
        self.levelsPlotItem.setLabel('bottom','Intensity')
        self.levelsPlotItem.getAxis('left').setTicks([[(0,'0')],[]])
        self.levelsPlotItem.getAxis('bottom').setTicks([[(0,'0'),(100,'100'),(200,'200')],[]])
        self.levelsPlotItem.setXRange(0,255)
        self.levelsPlot = self.levelsPlotItem.plot(np.zeros(256))
        self.lowLevelLine = pg.InfiniteLine(pos=0,pen='r',movable=True,bounds=(0,254))
        self.lowLevelLine.sigPositionChangeFinished.connect(self.lowLevelLineCallback)
        self.levelsPlotItem.addItem(self.lowLevelLine)
        self.highLevelLine = pg.InfiniteLine(pos=255,pen='r',movable=True,bounds=(1,255))
        self.highLevelLine.sigPositionChangeFinished.connect(self.highLevelLineCallback)
        self.levelsPlotItem.addItem(self.highLevelLine)
        
        # alpha control
        self.normDisplayCheckbox = QtGui.QCheckBox('Normalize Display')
        self.normDisplayCheckbox.stateChanged.connect(self.normDisplayCheckboxCallback) 
        
        self.alphaEditLayout = QtGui.QFormLayout()
        self.alphaEdit = QtGui.QLineEdit('')
        self.alphaEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.alphaEdit.editingFinished.connect(self.alphaEditCallback)
        self.alphaEditLayout.addRow('Alpha:',self.alphaEdit)
        
        self.alphaSlider = QtGui.QSlider()
        self.alphaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.alphaSlider.setRange(0,100)
        self.alphaSlider.setValue(100)
        self.alphaSlider.setSingleStep(1)
        self.alphaSlider.sliderReleased.connect(self.alphaSliderCallback)
        
        self.alphaControlLayout = QtGui.QGridLayout()
        self.alphaControlLayout.addLayout(self.alphaEditLayout,0,0,1,2)
        self.alphaControlLayout.addWidget(self.alphaSlider,0,2,1,2)
        self.alphaControlLayout.addWidget(self.normDisplayCheckbox,1,1,1,2,alignment=QtCore.Qt.AlignHCenter)
        
        # main layout
        nGridRows = 18
        nGridCols = 4
        self.mainWidget = QtGui.QWidget()
        self.mainWin.setCentralWidget(self.mainWidget)
        self.mainLayout = QtGui.QGridLayout()
        for row in range(nGridRows):
            self.mainLayout.setRowMinimumHeight(row,winHeight/nGridRows)
            self.mainLayout.setRowStretch(row,1)
        for col in range(nGridCols):
            self.mainLayout.setColumnMinimumWidth(col,winWidth/nGridCols)
            self.mainLayout.setColumnStretch(col,1)
        self.mainWidget.setLayout(self.mainLayout)
        self.mainLayout.addWidget(self.imageLayout,0,0,nGridRows,nGridCols/2)
        self.mainLayout.addWidget(self.fileListbox,0,2,5,2)
        self.mainLayout.addLayout(self.fileInfoLayout,5,2,6,1)
        self.mainLayout.addLayout(self.viewControlLayout,11,2,3,1)
        self.mainLayout.addLayout(self.rangeControlLayout,14,2,4,1)
        self.mainLayout.addWidget(self.levelsPlotWidget,5,3,6,1)
        self.mainLayout.addLayout(self.alphaControlLayout,11,3,2,1)
        self.mainWin.show()
        
    def mainWinResizeCallback(self,event):
        if len(self.imageObjs)>0 and len(self.checkedFileIndex)>0:
            self.setImageRange()
            self.displayImage()
        
    def mainWinCloseCallback(self,event):
        event.accept()
                   
    def openFile(self):
        filePaths,fileType = QtGui.QFileDialog.getOpenFileNamesAndFilter(self.mainWin,'Choose File(s)',self.fileOpenPath,'Images (*.tif *.jpg);;Bruker Dir (*.xml);;Bruker Dir + Siblings (*.xml);;Leica Confocal (*.tif);;Numpy Array (*npy);;Allen Atlas (*.nrrd)',self.fileOpenType)
        if len(filePaths)<1:
            return
        self.fileOpenPath = os.path.dirname(filePaths[0])
        self.fileOpenType = fileType
        if fileType=='Bruker Dir + Siblings (*.xml)':
            dirPath = os.path.dirname(os.path.dirname(filePaths[0]))
            filePaths = []
            for item in os.listdir(dirPath):
                itemPath = os.path.join(dirPath,item)
                if os.path.isdir(itemPath):
                    for f in os.listdir(itemPath):
                        if f[-4:]=='.xml':
                            fpath = os.path.join(itemPath,f)
                            if minidom.parse(fpath).getElementsByTagName('Sequence').item(0).getAttribute('type') in ('ZSeries','Single'):
                                filePaths.append(fpath)
        for filePath in filePaths:
            self.imageObjs.append(ImageObj(filePath,fileType))
            self.fileListbox.addItem(filePath)
            if len(self.imageObjs)>1:
                self.fileListbox.item(self.fileListbox.count()-1).setCheckState(QtCore.Qt.Unchecked)
            else:
                self.fileListbox.item(self.fileListbox.count()-1).setCheckState(QtCore.Qt.Checked)
                self.checkedFileIndex = [0]
                self.selectedFileIndex = [0]
                self.fileListbox.blockSignals(True)
                self.fileListbox.setCurrentRow(0)
                self.fileListbox.blockSignals(False)
                self.initImage()
                self.displayImage()
        if self.stitchCheckbox.isChecked():
            self.stitchPos = np.concatenate((self.stitchPos,np.full((len(filePaths),3),np.nan)))
        
    def saveImage(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.tif')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        yRange,xRange,_ = self.getImageRange()
        cv2.imwrite(filePath,self.image[yRange[0]:yRange[1],xRange[0]:xRange[1],::-1])
        
    def saveVolume(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.tif')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        currentImage = self.currentImageNum
        yRange,xRange,zRange = self.getImageRange()
        for i in range(zRange[0]+1,zRange[1]+1):
            self.currentImageNum = i
            self.updateImage()
            cv2.imwrite(filePath[:-4]+'_'+str(i)+'.tif',self.image[yRange[0]:yRange[1],xRange[0]:xRange[1],::-1])
        self.currentImageNum = currentImage
        
    def initImage(self):
        imageObj = self.imageObjs[self.checkedFileIndex[0]]
        self.channelListbox.blockSignals(True)
        self.channelListbox.clear()
        for ch in range(imageObj.data.shape[3]):
            self.channelListbox.addItem('Ch'+str(ch))
        self.channelListbox.setCurrentRow(0)
        self.channelListbox.blockSignals(False)
        self.selectedChannelIndex = [0]
        if self.sliceButton.isChecked():
            self.imageNumEdit.setText('1')
        self.currentImageNum = 1 
        self.displayImageRange()
        self.setImageRangeLimits()
        self.setImageRange()
        self.displayImageLevels()
        self.displayImage()
        
    def resetImageInfo(self):
        if self.stitchCheckbox.isChecked():
            self.stitchCheckbox.setChecked(False)
        self.channelListbox.blockSignals(True)
        self.channelListbox.clear()
        self.channelListbox.blockSignals(False)
        self.imageNumEdit.setText('')
        self.imageDimensionsLabel.setText('XYZ Dimensions: ')
        self.imagePixelSizeLabel.setText('XYZ Pixel Size (\u03BCm): ')
        self.xRangeLowEdit.setText('')
        self.xRangeHighEdit.setText('')
        self.yRangeLowEdit.setText('')
        self.yRangeHighEdit.setText('')
        self.zRangeLowEdit.setText('')
        self.zRangeHighEdit.setText('')
        self.displayImageLevels()
        self.imageItem.setImage(np.zeros((2,2,3),dtype=np.uint8).transpose((1,0,2)),autoLevels=False)
        
    def displayImageRange(self):
        if self.stitchCheckbox.isChecked():
            shape = self.stitchShape
            rng = self.stitchRange
        else:
            imageObj = self.imageObjs[self.checkedFileIndex[0]]
            shape = imageObj.data.shape
            rng = imageObj.range
        self.imageDimensionsLabel.setText('XYZ Dimensions: '+str(shape[1])+', '+str(shape[0])+', '+str(shape[2]))
        self.xRangeLowEdit.setText(str(rng[1][0]+1))
        self.xRangeHighEdit.setText(str(rng[1][1]))
        self.yRangeLowEdit.setText(str(rng[0][0]+1))
        self.yRangeHighEdit.setText(str(rng[0][1]))
        self.zRangeLowEdit.setText(str(rng[2][0]+1))
        self.zRangeHighEdit.setText(str(rng[2][1]))
        self.displayPixelSize()
        
    def displayPixelSize(self):
        pixelSize = self.imageObjs[self.checkedFileIndex[0]].pixelSize
        self.imagePixelSizeLabel.setText(u'XYZ Pixel Size (\u03BCm): '+str(pixelSize[1])+', '+str(pixelSize[0])+', '+str(pixelSize[2]))
    
    def displayImageLevels(self):
        fileInd = list(set(self.checkedFileIndex) & set(self.selectedFileIndex))
        if len(fileInd)>0:
            isSet = False
            pixIntensityHist = np.zeros(256)
            for i in fileInd:
                chInd = [ch for ch in self.selectedChannelIndex if ch <self.imageObjs[i].data.shape[3]]
                if len(chInd)>0:
                    hist,_ = np.histogram(self.imageObjs[i].data[:,:,:,chInd],bins=256,range=(0,256))
                    pixIntensityHist += hist
                    if not isSet:
                        self.lowLevelLine.setValue(self.imageObjs[i].levels[chInd[0]][0])
                        self.highLevelLine.setValue(self.imageObjs[i].levels[chInd[0]][1])
                        self.alphaEdit.setText(str(self.imageObjs[i].alpha[chInd[0]]))
                        self.alphaSlider.setValue(self.imageObjs[i].alpha[chInd[0]]*100)
                        isSet = True
            pixIntensityHist[pixIntensityHist<1] = 1
            pixIntensityHist = np.log10(pixIntensityHist)
            self.levelsPlot.setData(pixIntensityHist)
            histMax = pixIntensityHist.max()
            self.levelsPlotItem.setYRange(0,round(histMax))
            self.levelsPlotItem.getAxis('left').setTicks([[(0,'0'),(int(histMax),'1e'+str(int(histMax)))],[]])
        else:
            self.lowLevelLine.setValue(0)
            self.highLevelLine.setValue(255)
            self.alphaEdit.setText('')
            self.alphaSlider.setValue(100)
            self.levelsPlot.setData(np.zeros(256))
            self.levelsPlotItem.setYRange(0,1)
            self.levelsPlotItem.getAxis('left').setTicks([[(0,'0'),(1,'1')],[]])        
        
    def setImageRange(self):
        # square viewBox to fill layout, then adjust aspect to match image range
        self.ignoreImageRangeChange = True
        viewBoxRect = self.imageLayout.viewRect()
        if viewBoxRect.width()>viewBoxRect.height():
            viewBoxRect.moveLeft((viewBoxRect.width()-viewBoxRect.height())/2)
            viewBoxRect.setWidth(viewBoxRect.height())
        else:
            viewBoxRect.moveTop((viewBoxRect.height()-viewBoxRect.width())/2)
            viewBoxRect.setHeight(viewBoxRect.width())
        yRange,xRange,_ = self.getImageRange()
        aspect = (xRange[1]-xRange[0])/(yRange[1]-yRange[0])
        if aspect>1:
            viewBoxRect.setHeight(viewBoxRect.width()/aspect)
            viewBoxRect.moveTop(viewBoxRect.top()+(viewBoxRect.width()-viewBoxRect.height())/2)
        else:
            viewBoxRect.setWidth(viewBoxRect.height()*aspect)
            viewBoxRect.moveLeft(viewBoxRect.left()+(viewBoxRect.height()-viewBoxRect.width())/2)
        self.imageViewBox.setGeometry(viewBoxRect)
        self.imageViewBox.setRange(xRange=xRange,yRange=yRange,padding=0)
        self.ignoreImageRangeChange = False
        
    def getImageRange(self):
        imageRange = self.stitchRange if self.stitchCheckbox.isChecked() else self.imageObjs[self.checkedFileIndex[0]].range
        return [imageRange[i] for i in self.imageShapeIndex]
        
    def setImageRangeLimits(self):
        self.ignoreImageRangeChange = True
        imageShape = self.stitchShape if self.stitchCheckbox.isChecked() else self.imageObjs[self.checkedFileIndex[0]].data.shape
        ymax,xmax = [imageShape[i] for i in self.imageShapeIndex[:2]]
        self.imageViewBox.setLimits(xMin=0,xMax=xmax,yMin=0,yMax=ymax,minXRange=3,maxXRange=xmax,minYRange=3,maxYRange=ymax)
        self.ignoreImageRangeChange = False
        
    def flipImageHorz(self):
        for fileInd in self.selectedFileIndex:
            for ch in range(self.imageObjs[fileInd].data.shape[3]):
                self.imageObjs[fileInd].data[:,:,:,ch] = self.imageObjs[fileInd].data[:,::-1,:,ch]
        self.displayImage()
            
    def flipImageVert(self):
        for fileInd in self.selectedFileIndex:
            for ch in range(self.imageObjs[fileInd].data.shape[3]):
                self.imageObjs[fileInd].data[:,:,:,ch] = self.imageObjs[fileInd].data[::-1,:,:,ch]
        self.displayImage()
        
    def displayImage(self,update=True):
        if update:
            self.updateImage()
        self.imageItem.setImage(self.image.transpose((1,0,2)),autoLevels=False)
        
    def updateImage(self):
        if self.stitchCheckbox.isChecked():
            imageShape = [self.stitchShape[i] for i in self.imageShapeIndex[:2]]
        else:
            imageShape = [self.imageObjs[self.checkedFileIndex[0]].data.shape[i] for i in self.imageShapeIndex[:2]]
        rgb = np.zeros((imageShape[0],imageShape[1],3))
        for fileInd in self.checkedFileIndex:
            imageObj = self.imageObjs[fileInd]
            if self.stitchCheckbox.isChecked():
                i,j = [slice(self.stitchPos[fileInd,i],self.stitchPos[fileInd,i]+imageObj.data.shape[i]) for i in self.imageShapeIndex[:2]]
            else:
                i,j = [slice(0,imageObj.data.shape[i]) for i in self.imageShapeIndex[:2]]
            for ch in self.selectedChannelIndex:
                if ch<imageObj.data.shape[3]:
                    channelData = self.getChannelData(imageObj,ch,fileInd)
                    if channelData is not None:
                        for k in imageObj.rgbInd[ch]:
                            if self.stitchCheckbox.isChecked():
                                rgb[i,j,k] = np.maximum(rgb[i,j,k],channelData)
                            else:
                                rgb[i,j,k] *= 1-imageObj.alpha[ch]
                                rgb[i,j,k] += channelData*imageObj.alpha[ch]
        if self.normDisplayCheckbox.isChecked():
            rgb -= rgb.min()
            rgb[rgb<0] = 0
            if rgb.any():
                rgb *= 255/rgb.max()
        self.image = rgb.round().astype(np.uint8)
        for region in self.selectedAtlasRegions:
            _,contours,_ = cv2.findContours(np.copy(self.getAtlasRegion(region,imageObj.range),order='C').astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(self.image,contours,-1,(255,255,255))
                    
    def getChannelData(self,imageObj,ch,fileInd):
        if self.sliceButton.isChecked():
            i = self.currentImageNum-1
            if self.stitchCheckbox.isChecked():
                i -= self.stitchPos[fileInd][self.imageShapeIndex[2]]
                if not 0<=i<imageObj.data.shape[self.imageShapeIndex[2]]:
                    return
        if self.zButton.isChecked():
            if self.sliceButton.isChecked():
                channelData = imageObj.data[:,:,i,ch]
            else:
                if self.stitchCheckbox.isChecked():
                    channelData = imageObj.data[:,:,:,ch].max(axis=2)
                else:
                    channelData = imageObj.data[:,:,imageObj.range[2][0]:imageObj.range[2][1],ch].max(axis=2)
        elif self.yButton.isChecked():
            if self.sliceButton.isChecked():
                channelData = imageObj.data[i,:,:,ch].T
            else:
                if self.stitchCheckbox.isChecked():
                    channelData = imageObj.data[:,:,:,ch].max(axis=0).T
                else:
                    channelData = imageObj.data[imageObj.range[0][0]:imageObj.range[0][1],:,:,ch].max(axis=0).T
        else:
            if self.sliceButton.isChecked():
                channelData = imageObj.data[:,i,:,ch]
            else:
                if self.stitchCheckbox.isChecked():
                    channelData = imageObj.data[:,:,:,ch].max(axis=1)
                else:
                    channelData = imageObj.data[:,imageObj.range[1][0]:imageObj.range[1][1],:,ch].max(axis=1)
        channelData = channelData.astype(float)-imageObj.levels[ch][0] 
        channelData[channelData<0] = 0
        channelData *= 255/(imageObj.levels[ch][1]-imageObj.levels[ch][0])
        channelData[channelData>255] = 255
        return channelData
        
    def getAtlasRegion(self,region,rng):
        if self.zButton.isChecked():
            if self.sliceButton.isChecked():
                a = self.atlasAnnotationData[:,:,self.currentImageNum-1]
                a = np.in1d(a,region).reshape(a.shape)
            else:
                a = self.atlasAnnotationData[:,:,rng[2][0]:rng[2][1]]
                a = np.in1d(a,region).reshape(a.shape).max(axis=2)
        elif self.yButton.isChecked():
            if self.sliceButton.isChecked():
                a = self.atlasAnnotationData[self.currentImageNum-1,:,:].T
                a = np.in1d(a,region).reshape(a.shape)
            else:
                a = self.atlasAnnotationData[rng[0][0]:rng[0][1],:,:]
                a = np.in1d(a,region).reshape(a.shape).max(axis=0).T
        else:
            if self.sliceButton.isChecked():
                a = self.atlasAnnotationData[:,self.currentImageNum-1,:]
                a = np.in1d(a,region).reshape(a.shape)
            else:
                a = self.atlasAnnotationData[:,rng[1][0]:rng[1][1],:]
                a = np.in1d(a,region).reshape(a.shape).max(axis=1)
        return a
        
    def mainWinKeyPressCallback(self,event):
        key = event.key()
        modifiers = QtGui.QApplication.keyboardModifiers()
        if key==44 and self.sliceButton.isChecked(): # <
            self.setImageNum(self.currentImageNum-1)
        elif key==46 and self.sliceButton.isChecked(): # >
            self.setImageNum(self.currentImageNum+1)
        elif self.stitchCheckbox.isChecked():
            if int(modifiers & QtCore.Qt.ShiftModifier)>0:
                move = 100
            elif int(modifiers & QtCore.Qt.ControlModifier)>0:
                move = 10
            else:
                move = 1
            ind = list(set(self.checkedFileIndex) & set(self.selectedFileIndex))
            if key==16777235: # up
                self.stitchPos[ind,0] -= move
            elif key==16777237: # down
                self.stitchPos[ind,0] += move
            elif key==16777234: # left
                self.stitchPos[ind,1] -= move
            elif key==16777236: # right
                self.stitchPos[ind,1] += move
            elif key==61: # plus
                self.stitchPos[ind,2] -= move
            elif key==45: # minus
                self.stitchPos[ind,2] += move
            else:
                return
            self.updateStitchShape()
        else:
            return
        self.displayImage()
        
    def fileListboxSelectionCallback(self):
        self.selectedFileIndex = getSelectedItemsIndex(self.fileListbox)
        self.displayImageLevels()
        
    def fileListboxItemClickedCallback(self,item):
        i = self.fileListbox.indexFromItem(item).row()
        if item.checkState()==QtCore.Qt.Checked:
            if i not in self.checkedFileIndex:
                self.checkedFileIndex.append(i)
                self.checkedFileIndex.sort()
                if self.stitchCheckbox.isChecked():
                    self.stitchPos[i,:] = 0
                    self.updateStitchShape()
                    self.displayImageLevels()
                    self.displayImage()
                else:
                    if len(self.checkedFileIndex)<1 or self.imageObjs[i].data.shape[:3]==self.imageObjs[self.checkedFileIndex[0]].data.shape[:3]:
                        if len(self.checkedFileIndex)>1:
                            self.imageObjs[i].range = copy.copy(self.imageObjs[self.checkedFileIndex[0]].range)
                            nCh = self.imageObjs[i].data.shape[3]
                            if nCh>self.channelListbox.count():
                                self.channelListbox.blockSignals(True)
                                for ch in range(nCh-self.channelListbox.count()-1,nCh):
                                    self.channelListbox.addItem('Ch'+str(ch))
                                self.channelListbox.blockSignals(False)
                        else:
                            self.initImage()
                        self.displayImageLevels()
                        self.displayImage()
                    else:
                        item.setCheckState(QtCore.Qt.Unchecked)
        else:
            if i in self.checkedFileIndex:
                self.checkedFileIndex.remove(i)
                if self.stitchCheckbox.isChecked():
                    self.stitchPos[i,:] = np.nan
                    self.updateStitchShape()
                    self.displayImageLevels()
                    self.displayImage()
                else:
                    if len(self.checkedFileIndex)<1:
                        self.resetImageInfo()
                    else:
                        self.displayImageLevels()
                        self.displayImage()
                    
    def stitchCheckboxCallback(self):
        if self.stitchCheckbox.isChecked():
            for i in range(self.fileListbox.count()):
                if i in self.selectedFileIndex:
                    self.fileListbox.item(i).setCheckState(QtCore.Qt.Checked)
                else:
                    self.fileListbox.item(i).setCheckState(QtCore.Qt.Unchecked)
            self.checkedFileIndex = copy.copy(self.selectedFileIndex)
            self.stitchPos = np.full((self.fileListbox.count(),3),np.nan)
            useStagePos = all([self.imageObjs[i].position is not None for i in self.selectedFileIndex])
            col = 0
            pos = [0,0,0]
            for i in self.selectedFileIndex:
                if useStagePos:
                    self.stitchPos[i,:] = self.imageObjs[i].position
                else:
                    if col>math.floor(len(self.selectedFileIndex)**0.5):
                        col = 0
                        pos[0] += self.imageObjs[i].data.shape[0]
                        pos[1] = 0
                    elif col>0:
                        pos[1] += self.imageObjs[i].data.shape[1]
                    col += 1
                    self.stitchPos[i,:] = pos
            self.holdStitchRange = False
            self.updateStitchShape()
            self.displayImageLevels()
            self.displayImage()
        else:
            for i in self.checkedFileIndex[1:]:
                self.fileListbox.item(i).setCheckState(QtCore.Qt.Unchecked)
            del(self.checkedFileIndex[1:])
            self.initImage()
    
    def updateStitchShape(self):
        self.stitchPos -= np.nanmin(self.stitchPos,axis=0)
        imageShapes = np.array([self.imageObjs[i].data.shape[0:3] for i in self.checkedFileIndex])
        self.stitchShape = (self.stitchPos[self.checkedFileIndex,:]+imageShapes).max(axis=0)
        if self.holdStitchRange:
            for i in (0,1,2):
                if self.stitchRange[i][1]>self.stitchShape[i]:
                    self.stitchRange[i][1] = self.stitchShape[i]
        else:
            self.stitchRange = [[0,self.stitchShape[i]] for i in (0,1,2)]
        self.setImageRangeLimits()
        self.setImageRange()
        self.displayImageRange()
                    
    def moveFileDownButtonCallback(self):
        for i,fileInd in reversed(list(enumerate(self.selectedFileIndex))):
            if fileInd<self.fileListbox.count()-1 and (i==len(self.selectedFileIndex)-1 or self.selectedFileIndex[i+1]-fileInd>1):
                item = self.fileListbox.takeItem(fileInd)
                self.fileListbox.insertItem(fileInd+1,item)
                self.fileListbox.setItemSelected(item,True)
                if fileInd in self.checkedFileIndex and fileInd+1 in self.checkedFileIndex:
                    n = self.checkedFileIndex.index(fileInd)
                    self.checkedFileIndex[n],self.checkedFileIndex[n+1] = self.checkedFileIndex[n+1],self.checkedFileIndex[n]
                elif fileInd in self.checkedFileIndex:
                    self.checkedFileIndex[self.checkedFileIndex.index(fileInd)] += 1
                elif fileInd+1 in self.checkedFileIndex:
                    self.checkedFileIndex[self.checkedFileIndex.index(fileInd+1)] -= 1
                self.imageObjs[fileInd],self.imageObjs[fileInd+1] = self.imageObjs[fileInd+1],self.imageObjs[fileInd]
        self.displayImage()
    
    def moveFileUpButtonCallback(self):
        for i,fileInd in enumerate(self.selectedFileIndex[:]):
            if fileInd>0 and (i==0 or fileInd-self.selectedFileIndex[i-1]>1):
                item = self.fileListbox.takeItem(fileInd)
                self.fileListbox.insertItem(fileInd-1,item)
                self.fileListbox.setItemSelected(item,True)
                if fileInd in self.checkedFileIndex and fileInd-1 in self.checkedFileIndex:
                    n = self.checkedFileIndex.index(fileInd)
                    self.checkedFileIndex[n-1],self.checkedFileIndex[n] = self.checkedFileIndex[n],self.checkedFileIndex[n-1]
                elif fileInd in self.checkedFileIndex:
                    self.checkedFileIndex[self.checkedFileIndex.index(fileInd)] -= 1
                elif fileInd-1 in self.checkedFileIndex:
                    self.checkedFileIndex[self.checkedFileIndex.index(fileInd-1)] += 1
                self.imageObjs[fileInd-1],self.imageObjs[fileInd] = self.imageObjs[fileInd],self.imageObjs[fileInd-1]
        self.displayImage()
    
    def removeFileButtonCallback(self):
        if self.stitchCheckbox.isChecked():
            self.stitchPos = np.delete(self.stitchPos,self.selectedFileIndex,axis=0)
        for fileInd in reversed(self.selectedFileIndex):
            if fileInd in self.checkedFileIndex:
                self.checkedFileIndex.remove(fileInd)
            self.imageObjs.remove(self.imageObjs[fileInd])
            self.fileListbox.takeItem(fileInd)
        self.selectedFileIndex = []
        if len(self.checkedFileIndex)<1:
            self.resetImageInfo()
        else:
            self.displayImageLevels()
            self.displayImage()
        
    def channelListboxCallback(self):
        self.selectedChannelIndex = getSelectedItemsIndex(self.channelListbox)
        self.displayImageLevels()
        self.displayImage()
        
    def channelColorMenuCallback(self):
        color = self.channelColorMenu.currentText()
        self.channelColorMenu.setCurrentIndex(0)
        if color!='Color':
            if color=='Red':
                rgbInd = (0,)
            elif color=='Green':
                rgbInd = (1,)
            elif color=='Blue':
                rgbInd = (2,)
            elif color=='Magenta':
                rgbInd = (0,2)
            else: # Gray
                rgbInd = (0,1,2)
            for fileInd in self.selectedFileIndex:
                for ch in self.selectedChannelIndex:
                    if ch<self.imageObjs[fileInd].data.shape[3]:
                        self.imageObjs[fileInd].rgbInd[ch] = rgbInd
        self.displayImage()
        
    def imageNumEditCallback(self):
        self.setImageNum(int(self.imageNumEdit.text()))
        self.displayImage()
        
    def setImageNum(self,imageNum):
        imageShape = self.stitchShape if self.stitchCheckbox.isChecked() else self.imageObjs[self.checkedFileIndex[0]].data.shape
        if imageNum<1:
            imageNum = 1
        elif imageNum>imageShape[self.imageShapeIndex[2]]:
            imageNum = imageShape[self.imageShapeIndex[2]]
        self.imageNumEdit.setText(str(imageNum))
        self.currentImageNum = imageNum
        
    def sliceProjButtonCallback(self):
        if self.sliceButton.isChecked():
            self.imageNumEdit.setEnabled(True)
            self.imageNumEdit.setText(str(self.currentImageNum))
        else:
            self.imageNumEdit.setEnabled(False)
            self.imageNumEdit.setText('')
        self.displayImage()
    
    def xyzButtonCallback(self):
        if self.sliceButton.isChecked():
            self.imageNumEdit.setText('1')
        self.currentImageNum = 1
        if self.zButton.isChecked():
            self.imageShapeIndex = (0,1,2)
        elif self.yButton.isChecked():
            self.imageShapeIndex = (2,1,0)
        else:
            self.imageShapeIndex = (0,2,1)
        self.setImageRangeLimits()
        self.setImageRange()
        self.displayImage()
        
    def zoomPanButtonCallback(self):
        if self.zoomPanButton.isChecked():
            self.imageViewBox.setMouseEnabled(x=True,y=True)
        else:
            self.imageViewBox.setMouseEnabled(x=False,y=False)
        
    def resetViewButtonCallback(self):
        if self.stitchCheckbox.isChecked():
            shape = self.stitchShape
            self.stitchRange = [[0,shape[i]] for i in (0,1,2)]
            self.holdStitchRange = False
        else:             
            for file in (set(self.checkedFileIndex) | set(self.selectedFileIndex)):
                shape = self.imageObjs[file].data.shape
                self.imageObjs[file].range = [[0,shape[i]] for i in (0,1,2)]
        self.xRangeLowEdit.setText('1')
        self.xRangeHighEdit.setText(str(shape[1]))
        self.yRangeLowEdit.setText('1')
        self.yRangeHighEdit.setText(str(shape[0]))
        self.zRangeLowEdit.setText('1')
        self.zRangeHighEdit.setText(str(shape[2]))
        self.setImageRange()
        if self.projectionButton.isChecked():
            self.displayImage()
        
    def xRangeLowEditCallback(self):
        newVal = int(self.xRangeLowEdit.text())
        xmax = int(self.xRangeHighEdit.text())
        if newVal<1:
            newVal = 1
        elif newVal>=xmax-1:
            newVal = xmax-1
        self.xRangeLowEdit.setText(str(newVal))
        self.setRange(newVal-1,1,0,self.xButton)
            
    def xRangeHighEditCallback(self):
        newVal = int(self.xRangeHighEdit.text())
        xmin = int(self.xRangeLowEdit.text())
        xmax = self.stitchShape[1] if self.stitchCheckbox.isChecked() else self.imageObjs[self.checkedFileIndex[0]].data.shape[1]
        if newVal<=xmin:
            newVal = xmin+1
        elif newVal>xmax:
            newVal = xmax
        self.xRangeHighEdit.setText(str(newVal))
        self.setRange(newVal,1,1,self.xButton)
        
    def yRangeLowEditCallback(self):
        newVal = int(self.yRangeLowEdit.text())
        ymax = int(self.yRangeHighEdit.text())
        if newVal<1:
            newVal = 1
        elif newVal>=ymax-1:
            newVal = ymax-1
        self.yRangeLowEdit.setText(str(newVal))
        self.setRange(newVal-1,0,0,self.yButton)
            
    def yRangeHighEditCallback(self):
        newVal = int(self.yRangeHighEdit.text())
        ymin = int(self.yRangeLowEdit.text())
        ymax = self.stitchShape[0] if self.stitchCheckbox.isChecked() else self.imageObjs[self.checkedFileIndex[0]].data.shape[0]
        if newVal<=ymin:
            newVal = ymin+1
        elif newVal>ymax:
            newVal = ymax
        self.yRangeHighEdit.setText(str(newVal))
        self.setRange(newVal,0,1,self.yButton)
        
    def zRangeLowEditCallback(self):
        newVal = int(self.zRangeLowEdit.text())
        zmax = int(self.zRangeHighEdit.text())
        if newVal<1:
            newVal = 1
        elif newVal>=zmax-1:
            newVal = zmax-1
        self.zRangeLowEdit.setText(str(newVal))
        self.setRange(newVal-1,2,0,self.zButton)
            
    def zRangeHighEditCallback(self):
        newVal = int(self.zRangeHighEdit.text())
        zmin = int(self.zRangeLowEdit.text())
        zmax = self.stitchShape[2] if self.stitchCheckbox.isChecked() else self.imageObjs[self.checkedFileIndex[0]].data.shape[2]
        if newVal<=zmin:
            newVal = zmin+1
        elif newVal>zmax:
            newVal = zmax
        self.zRangeHighEdit.setText(str(newVal))
        self.setRange(newVal,2,1,self.zButton)
            
    def setRange(self,newVal,ax,rangeInd,button):
        if self.stitchCheckbox.isChecked():
            if newVal<=self.stitchShape[ax]:
                self.stitchRange[ax][rangeInd] = newVal
            self.holdStitchRange = True
        else:
            for fileInd in self.checkedFileIndex:
                if newVal<=self.imageObjs[fileInd].data.shape[ax]:
                    self.imageObjs[fileInd].range[ax][rangeInd] = newVal
        if button.isChecked():
            if self.projectionButton.isChecked():
                self.displayImage()
        else:
            self.setImageRange()
        
    def imageRangeChanged(self):
        if len(self.imageObjs)<1 or self.ignoreImageRangeChange:
            return
        newRange = [[int(round(n)) for n in x] for x in reversed(self.imageViewBox.viewRange())]
        if self.zButton.isChecked():
            self.xRangeLowEdit.setText(str(newRange[1][0]+1))
            self.xRangeHighEdit.setText(str(newRange[1][1]))
            self.yRangeLowEdit.setText(str(newRange[0][0]+1))
            self.yRangeHighEdit.setText(str(newRange[0][1]))
        elif self.yButton.isChecked():
            self.xRangeLowEdit.setText(str(newRange[1][0]+1))
            self.xRangeHighEdit.setText(str(newRange[1][1]))
            self.zRangeLowEdit.setText(str(newRange[0][0]+1))
            self.zRangeHighEdit.setText(str(newRange[0][1]))
        else:
            self.zRangeLowEdit.setText(str(newRange[1][0]+1))
            self.zRangeHighEdit.setText(str(newRange[1][1]))
            self.yRangeLowEdit.setText(str(newRange[0][0]+1))
            self.yRangeHighEdit.setText(str(newRange[0][1]))
        if self.stitchCheckbox.isChecked():
            self.updateRange(self.stitchRange,self.stitchShape,newRange,self.imageShapeIndex[:2])
            self.holdStitchRange = True
        else:
            for fileInd in self.checkedFileIndex:
                self.updateRange(self.imageObjs[fileInd].range,self.imageObjs[fileInd].data.shape,newRange,self.imageShapeIndex[:2])
        self.setImageRange()
        
    def updateRange(self,itemRange,itemShape,newRange,axes=(0,1,2)):
        for ax,rng in zip(axes,newRange):
            if rng[0]<0:
                rng[0] = 0
            if rng[1]>itemShape[ax]:
                rng[1] = itemShape[ax]
            itemRange[ax] = rng
        
    def saveRange(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.p')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        rng = [[int(self.yRangeLowEdit.text())-1,int(self.yRangeHighEdit.text())],[int(self.xRangeLowEdit.text())-1,int(self.xRangeHighEdit.text())],[int(self.zRangeLowEdit.text())-1,int(self.zRangeHighEdit.text())]]
        pickle.dump(rng,open(filePath,'wb'))
    
    def loadRange(self):
        filePath = QtGui.QFileDialog.getOpenFileName(self.mainWin,'Choose File',self.fileOpenPath,'*.p')
        if filePath=='':
            return
        self.fileOpenPath = os.path.dirname(filePath)
        rng = pickle.load(open(filePath,'rb'))
        self.xRangeLowEdit.setText(str(rng[1][0]+1))
        self.xRangeHighEdit.setText(str(rng[1][1]))
        self.yRangeLowEdit.setText(str(rng[0][0]+1))
        self.yRangeHighEdit.setText(str(rng[0][1]))
        self.zRangeLowEdit.setText(str(rng[2][0]+1))
        self.zRangeHighEdit.setText(str(rng[2][1]))
        if self.stitchCheckbox.isChecked():
            self.updateRange(self.stitchRange,self.stitchShape,rng)
            self.holdStitchRange = True
        else:
            for fileInd in self.checkedFileIndex:
                self.updateRange(self.imageObjs[fileInd].range,self.imageObjs[fileInd].data.shape,rng)
        self.setImageRange()
        
    def lowLevelLineCallback(self):
        newVal = self.lowLevelLine.value()
        #self.highLevelLine.setBounds((newVal+1,255))
        self.setLevels(newVal,0)
         
    def highLevelLineCallback(self):
        newVal = self.highLevelLine.value()
        #self.lowLevelLine.setBounds((0,newVal-1))
        self.setLevels(newVal,1)
        
    def setLevels(self,newVal,levelsInd):
        for fileInd in self.selectedFileIndex:
            for ch in self.selectedChannelIndex:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].levels[ch][levelsInd] = newVal
        self.displayImage()
        
    def normDisplayCheckboxCallback(self):
        self.displayImage()
        
    def alphaEditCallback(self):
        newVal = round(float(self.alphaEdit.text()),2)
        if newVal<0:
            newVal = 0
        elif newVal>1:
            newVal = 1
        self.alphaEdit.setText(str(newVal))
        self.alphaSlider.setValue(newVal*100)
        self.setAlpha(newVal)
    
    def alphaSliderCallback(self):
        newVal = self.alphaSlider.value()/100
        self.alphaEdit.setText(str(newVal))
        self.setAlpha(newVal)
        self.displayImage()
        
    def setAlpha(self,newVal):
        for fileInd in self.selectedFileIndex:
            for ch in self.selectedChannelIndex:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].alpha[ch] = newVal
        self.displayImage()
        
    def setPixelSize(self):
        if self.mainWin.sender() is self.toolsMenuPixelSizeXY:
            dim = 'XY'
            ind = (0,1)
        else:
            dim = 'Z'
            ind = (2,)
        val,ok = QtGui.QInputDialog.getDouble(self.mainWin,'Set '+dim+' Pixel Size','\u03BCm/pixel:',0,min=0,decimals=4)
        if ok and val>0:
            for file in self.selectedFileIndex:
                for i in ind:
                    self.imageObjs[file].pixelSize[i] = val
            self.displayPixelSize()
        
    def setRelativeIntensityThresh(self):
        val,ok = QtGui.QInputDialog.getDouble(self.mainWin,'Set Intensity Threshold','Fraction of brightest pixel in region:',value=self.relativeIntensityThresh,min=0.01,max=0.99,decimals=2)
        if ok:
            self.relativeIntensityThresh = val
        
    def setAbsIntensityThresh(self):
        val,ok = QtGui.QInputDialog.getInt(self.mainWin,'Set Intensity Threshold','Minimum pixel intensity value:',value=self.absIntensityThresh,min=0,max=254)
        if ok:
            self.absIntensityThresh = val
        
    def measureOverlap(self):
        ok = True
        files = list(set(self.checkedFileIndex) & set(self.selectedFileIndex))
        if len(files)==1:
            if len(self.selectedChannelIndex)==2:
                ch1AboveThresh = self.getDataInRegion(self.imageObjs[files[0]],self.selectedChannelIndex[0],True)
                ch2AboveThresh = self.getDataInRegion(self.imageObjs[files[0]],self.selectedChannelIndex[1],True)
            else:
                ok = False
        elif len(files)==2:
            if len(self.selectedChannelIndex)==1:
                ch1AboveThresh = self.getDataInRegion(self.imageObjs[files[0]],self.selectedChannelIndex[0],True)
                ch2AboveThresh = self.getDataInRegion(self.imageObjs[files[1]],self.selectedChannelIndex[0],True)
            else:
                ok = False
        else:
            ok = False
        if ok:
            overlap = np.count_nonzero(np.logical_and(ch1AboveThresh,ch2AboveThresh))
            pixelsInRegion = np.count_nonzero(self.getDataInRegion(self.imageObjs[files[0]],self.selectedChannelIndex[0],False))
            ch1AboveThresh = np.count_nonzero(ch1AboveThresh)
            ch2AboveThresh = np.count_nonzero(ch2AboveThresh)
            print(ch1AboveThresh/pixelsInRegion)
            print(ch2AboveThresh/pixelsInRegion)
            print(overlap/pixelsInRegion)
            print(overlap/ch1AboveThresh)
            print(overlap/ch2AboveThresh)
        else:
            QtGui.QMessageBox(self.mainWin,QtGui.QMessageBox.Information,'Select one file and 2 channels or two files and one channel to compare')
            
    def findContour(self):
        files = list(set(self.checkedFileIndex) & set(self.selectedFileIndex))
        if len(files)>0:
            imageObj = self.imageObjs[files[0]]
            inRegion = self.getDataInRegion(imageObj,self.selectedChannelIndex[0],True)
            if self.zButton.isChecked():
                if self.sliceButton.isChecked():
                    inRegion = inRegion[:,:,self.currentImageNum-1-imageObj.range[2][0]]
                else:
                    inRegion = inRegion.max(axis=2)
            elif self.yButton.isChecked():
                if self.sliceButton.isChecked():
                    inRegion = inRegion[self.currentImageNum-1-imageObj.range[0][0],:,:].T
                else:
                    inRegion = inRegion.max(axis=0).T
            else:
                if self.sliceButton.isChecked():
                    inRegion = inRegion[:,self.currentImageNum-1-imageObj.range[1][0],:]
                else:
                    inRegion = inRegion.max(axis=1)
            _,contours,_ = cv2.findContours(np.copy(inRegion,order='C').astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            ind = np.argmax([cont.shape[0] for cont in contours])
            yRange,xRange,_ = self.getImageRange()
            contours[ind][:,0,0] += xRange[0]
            contours[ind][:,0,1] += yRange[0]
            cv2.drawContours(self.image,contours,ind,(255,255,0))
            self.contour = contours[ind]
            self.displayImage(update=False)
            if self.toolsMenuContourAutoSave.isChecked():
                self.saveContour()
    
    def saveContour(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.p')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        pickle.dump(self.contour,open(filePath,'wb'))
    
    def loadContour(self):
        filePaths = QtGui.QFileDialog.getOpenFileNames(self.mainWin,'Choose Files',self.fileOpenPath,'*.p')
        if len(filePaths)<1:
            return
        self.fileOpenPath = os.path.dirname(filePaths[0])
        for file in filePaths:
            contour = pickle.load(open(file,'rb'))
            cv2.drawContours(self.image,[contour],0,(255,255,0))
        self.displayImage(update=False)
        
    def findInRegion(self):
        inRegion = []
        for file in self.selectedFileIndex:
            inRegion.append(self.getDataInRegion(self.imageObjs[file],self.selectedChannelIndex[0]))
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.p')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        if len(inRegion)<2:
            inRegion = inRegion[0]
        pickle.dump(inRegion,open(filePath,'wb'))        
        
    def getDataInRegion(self,imageObj,ch,applyThresh):
        r = imageObj.range
        rangeInd = np.s_[r[0][0]:r[0][1],r[1][0]:r[1][1],r[2][0]:r[2][1]]
        data = imageObj.data[:,:,:,ch][rangeInd]
        inRegion = np.ones(data.shape,dtype=np.bool)
        if len(self.selectedAtlasRegions)>0:
            a = self.atlasAnnotationData[rangeInd]
            for region in self.selectedAtlasRegions:
                inRegion = np.logical_and(inRegion,np.in1d(a,region).reshape(a.shape))
        if applyThresh:
            inRegion = np.logical_and(inRegion,data>self.absIntensityThresh)
            inRegion = np.logical_and(inRegion,data>self.relativeIntensityThresh*data[inRegion].max())
        return inRegion
        
    def setAtlasRegions(self):
        if self.atlasAnnotationData is None:
            filePath = QtGui.QFileDialog.getOpenFileName(self.mainWin,'Choose Annotation File',self.fileOpenPath,'*.nrrd')
            if filePath=='':
                for region in self.atlasRegionsMenu:
                    if region.isChecked():
                        region.setChecked(False)
                return
            self.fileSavePath = os.path.dirname(filePath)
            self.atlasAnnotationData,_ = nrrd.read(filePath)
            self.atlasAnnotationData = self.atlasAnnotationData.transpose((1,2,0))
        self.selectedAtlasRegions = []
        for i,region in enumerate(self.atlasRegionsMenu):
            if region.isChecked():
                self.selectedAtlasRegions.append(self.atlasRegionIDs[i])
        self.displayImage()
        
    def clearAtlasRegions(self):
        if len(self.selectedAtlasRegions)>0:
            for region in self.atlasRegionsMenu:
                if region.isChecked():
                    region.setChecked(False)
            self.selectedAtlasRegions = []
            self.displayImage()


class ImageObj():
    
    def __init__(self,filePath,fileType):
        if fileType=='Images (*.tif *.jpg)':
            self.data = cv2.imread(filePath,cv2.IMREAD_UNCHANGED)
            if self.data.dtype!='uint8':
                self.data = make8bit(self.data)
            if len(self.data.shape)<3:
                self.data = self.data[:,:,None,None]
            else:
                self.data = self.data[:,:,None,:]
            self.pixelSize = [None]*3
            self.position = None
        elif fileType in ('Bruker Dir (*.xml)','Bruker Dir + Siblings (*.xml)'):
            xml = minidom.parse(filePath)
            pvStateValues = xml.getElementsByTagName('PVStateValue')
            linesPerFrame = int(pvStateValues[7].getAttribute('value'))
            pixelsPerLine = int(pvStateValues[15].getAttribute('value'))
            frames = xml.getElementsByTagName('Frame')
            self.data = np.zeros((linesPerFrame,pixelsPerLine,len(frames),len(frames[0].getElementsByTagName('File'))))
            zpos = []
            for i,frame in enumerate(frames):
                zpos.append(float(frame.getElementsByTagName('SubindexedValue')[2].getAttribute('value')))
                for ch,tifFile in enumerate(frame.getElementsByTagName('File')):
                    self.data[:,:,i,ch] = cv2.imread(os.path.join(os.path.dirname(filePath),tifFile.getAttribute('filename')),cv2.IMREAD_UNCHANGED)
            self.data = make8bit(self.data)
            self.pixelSize = [round(float(pvStateValues[9].getElementsByTagName('IndexedValue')[0].getAttribute('value')),4)]*2
            if len(frames)>1:
                self.pixelSize.append(round(zpos[1]-zpos[0],4))
            else:
                self.pixelSize.append(None)
            xpos = float(pvStateValues[17].getElementsByTagName('SubindexedValue')[0].getAttribute('value'))
            ypos = float(pvStateValues[17].getElementsByTagName('SubindexedValue')[1].getAttribute('value'))
            self.position = [int(ypos/self.pixelSize[0]),int(xpos/self.pixelSize[1]),int(zpos[0]/self.pixelSize[2])] 
        elif fileType=='Numpy Array (*npy)':
            self.data = np.load(filePath)
            if self.data.dtype!='uint8':
                self.data = make8bit(self.data)
            if len(self.data.shape)<2:
                self.data = self.data[:,None,None,None]
            elif len(self.data.shape)<3:
                self.data = self.data[:,:,None,None]
            elif len(self.data.shape)<4:
                self.data = self.data[:,:,:,None]
            self.pixelSize = [None]*3
            self.position = None
        elif fileType=='Allen Atlas (*.nrrd)':
            self.data,_ = nrrd.read(filePath)
            self.data = make8bit(self.data).transpose((1,2,0))[:,:,:,None]
            self.pixelSize = [25.0]*3
            self.position = None
        self.range = [[0,self.data.shape[i]] for i in (0,1,2)]
        self.levels = [[0,255] for i in range(self.data.shape[3])]
        self.alpha = [1 for i in range(self.data.shape[3])]
        if self.data.shape[3]==2:
            self.rgbInd = [(0,2),(1,)]
        elif self.data.shape[3]==3:
            self.rgbInd = [(0,),(1,),(2,)]
        else:
            self.rgbInd = [(0,1,2) for i in range(self.data.shape[3])]
                
                
def make8bit(data):
    data = data.astype(float)
    data *= 255/data.max()
    return data.round().astype(np.uint8)
            

def getSelectedItemsIndex(listbox):
    selectedItemsIndex = []
    for i in range(listbox.count()):
        if listbox.item(i).isSelected():
            selectedItemsIndex.append(i)
    return selectedItemsIndex


if __name__=="__main__":
    start()