# -*- coding: utf-8 -*-
"""
Image visualization and analysis GUI

@author: samgale
"""

from __future__ import division
import sip
sip.setapi('QString', 2)
import os, math, cv2, nrrd
from xml.dom import minidom
import numpy as np
from PyQt4 import QtGui, QtCore
import pyqtgraph as pg


def start():
    app = QtGui.QApplication.instance()
    if app is None:
        app = QtGui.QApplication([])
    imageGuiObj = ImageGui(app)
    app.exec_()


class ImageGui():
    
    def __init__(self,app):
        self.app = app
        self.fileOpenPath = os.path.dirname(os.path.realpath(__file__))
        self.fileOpenType = 'Images (*.tif *.jpg)'
        self.fileSavePath = self.fileOpenPath
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
        self.imageMenuPixelSize = self.imageMenu.addMenu('Set Pixel Size')
        self.imageMenuPixelSizeXY = QtGui.QAction('XY',self.mainWin)
        self.imageMenuPixelSizeXY.triggered.connect(self.setPixelSize)
        self.imageMenuPixelSizeZ = QtGui.QAction('Z',self.mainWin)
        self.imageMenuPixelSizeZ.triggered.connect(self.setPixelSize)
        self.imageMenuPixelSize.addActions([self.imageMenuPixelSizeXY,self.imageMenuPixelSizeZ])        
        
        self.imageMenuFlip = self.imageMenu.addMenu('Flip')
        self.imageMenuFlipHorz = QtGui.QAction('Horizontal',self.mainWin)
        self.imageMenuFlipHorz.triggered.connect(self.flipImageHorz)
        self.imageMenuFlipVert = QtGui.QAction('Vertical',self.mainWin)
        self.imageMenuFlipVert.triggered.connect(self.flipImageVert)
        self.imageMenuFlip.addActions([self.imageMenuFlipHorz,self.imageMenuFlipVert])
        
        self.imageMenuRotate90 = QtGui.QAction('Rotate 90',self.mainWin)
        self.imageMenuRotate90.triggered.connect(self.rotateImage90)
        self.imageMenu.addAction(self.imageMenuRotate90)
        
        self.imageMenuRange = self.imageMenu.addMenu('Range')
        self.imageMenuRangeLoad = QtGui.QAction('Load',self.mainWin)
        self.imageMenuRangeLoad.triggered.connect(self.loadImageRange)
        self.imageMenuRangeSave = QtGui.QAction('Save',self.mainWin)
        self.imageMenuRangeSave.triggered.connect(self.saveImageRange)
        self.imageMenuRange.addActions([self.imageMenuRangeLoad,self.imageMenuRangeSave])
        
        # atlas menu
        self.atlasMenu = self.menuBar.addMenu('Atlas')
        self.atlasMenuSelect = self.atlasMenu.addMenu('Select Regions')
        self.atlasAnnotationData = None
        self.atlasRegionLabels = ('LGd','LGv','LP','LD','VISp','VISpl','VISpm','VISli','VISpor')
        self.atlasRegionIDs = (170,178,218,155,(593,821,721,778,33,305),(750,269,869,902,377,393),(805,41,501,565,257,469),(312782578,312782582,312782586,312782590,312782594,312782598),(312782632,312782636,312782640,312782644,312782648,312782652))
        self.atlasRegionMenu = []
        for region in self.atlasRegionLabels:
            self.atlasRegionMenu.append(QtGui.QAction(region,self.mainWin,checkable=True))
            self.atlasRegionMenu[-1].triggered.connect(self.setAtlasRegions)
        self.atlasMenuSelect.addActions(self.atlasRegionMenu)
        
        self.atlasMenuClear = QtGui.QAction('Clear All',self.mainWin)
        self.atlasMenuClear.triggered.connect(self.clearAtlasRegions)
        self.atlasMenu.addAction(self.atlasMenuClear)
        
        # image windows
        self.imageLayout = pg.GraphicsLayoutWidget()
        self.ignoreImageRangeChange = False
        self.imageViewBox = [pg.ViewBox(invertY=True,enableMouse=False,enableMenu=False) for _ in range(4)]
        self.imageItem = [pg.ImageItem() for _ in range(4)]
        for viewBox,imgItem in zip(self.imageViewBox,self.imageItem):
            viewBox.sigRangeChanged.connect(self.imageRangeChanged)
            viewBox.addItem(imgItem)
            self.imageLayout.addItem(viewBox)
        
        # file selection
        self.fileListbox = QtGui.QListWidget()
        self.fileListbox.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.fileListbox.itemSelectionChanged.connect(self.fileListboxSelectionCallback)
        self.fileListbox.itemClicked.connect(self.fileListboxItemClickedCallback)
        
        self.moveFileDownButton = QtGui.QToolButton()
        self.moveFileDownButton.setArrowType(QtCore.Qt.DownArrow)
        self.moveFileDownButton.clicked.connect(self.moveFileDownButtonCallback)
        
        self.moveFileUpButton = QtGui.QToolButton()
        self.moveFileUpButton.setArrowType(QtCore.Qt.UpArrow)
        self.moveFileUpButton.clicked.connect(self.moveFileUpButtonCallback)
        
        self.removeFileButton = QtGui.QPushButton('Remove')
        self.removeFileButton.clicked.connect(self.removeFileButtonCallback)
        
        self.stitchCheckbox = QtGui.QCheckBox('Stitch')
        self.stitchCheckbox.stateChanged.connect(self.stitchCheckboxCallback)
        
        self.viewChannelsCheckbox = QtGui.QCheckBox('Channel View')
        self.viewChannelsCheckbox.stateChanged.connect(self.viewChannelsCheckboxCallback)
        
        self.view3DCheckbox = QtGui.QCheckBox('3D View')
        self.view3DCheckbox.stateChanged.connect(self.view3DCheckboxCallback)
        
        self.fileSelectLayout = QtGui.QGridLayout()
        self.fileSelectLayout.addWidget(self.moveFileDownButton,0,0,1,1)
        self.fileSelectLayout.addWidget(self.moveFileUpButton,0,1,1,1)
        self.fileSelectLayout.addWidget(self.removeFileButton,0,2,1,2)
        self.fileSelectLayout.addWidget(self.stitchCheckbox,0,4,1,2)
        self.fileSelectLayout.addWidget(self.viewChannelsCheckbox,0,6,1,2)
        self.fileSelectLayout.addWidget(self.view3DCheckbox,0,8,1,2)
        self.fileSelectLayout.addWidget(self.fileListbox,1,0,9,10)
        
        # window and channel selection
        self.windowListbox = QtGui.QListWidget()
        self.windowListbox.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        for n in range(4):
            self.windowListbox.addItem('Window '+str(n+1))
        self.windowListbox.setCurrentRow(0)
        self.windowListbox.itemSelectionChanged.connect(self.windowListboxCallback)
        
        self.linkWindowsCheckbox = QtGui.QCheckBox('Link Windows')
        self.linkWindowsCheckbox.stateChanged.connect(self.linkWindowsCheckboxCallback)
        
        self.channelListbox = QtGui.QListWidget()
        self.channelListbox.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.channelListbox.itemSelectionChanged.connect(self.channelListboxCallback)
        
        self.channelColorMenu = QtGui.QComboBox()
        self.channelColorMenu.addItems(('Channel Color','Gray','Red','Green','Blue','Magenta'))
        self.channelColorMenu.currentIndexChanged.connect(self.channelColorMenuCallback)
        
        self.windowChannelLayout = QtGui.QGridLayout()
        self.windowChannelLayout.addWidget(self.linkWindowsCheckbox,0,0,1,1)
        self.windowChannelLayout.addWidget(self.windowListbox,1,0,4,1) 
        self.windowChannelLayout.addWidget(self.channelColorMenu,0,2,1,1)
        self.windowChannelLayout.addWidget(self.channelListbox,1,2,4,1)
        
        # view control
        self.imageDimensionsLabel = QtGui.QLabel('XYZ Dimensions: ')
        self.imagePixelSizeLabel = QtGui.QLabel('XYZ Pixel Size (\u03BCm): ')        

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
        self.sliceProjButtons = (self.sliceButton,self.projectionButton)
        
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
        self.xyzButtons = (self.xButton,self.yButton,self.zButton)
        
        self.viewControlLayout = QtGui.QGridLayout()
        self.viewControlLayout.addWidget(self.imageDimensionsLabel,0,0,1,3)
        self.viewControlLayout.addWidget(self.imagePixelSizeLabel,1,0,1,3)
        self.viewControlLayout.addLayout(self.imageNumEditLayout,2,0,1,2)
        self.viewControlLayout.addWidget(self.sliceProjGroupBox,3,0,2,2)
        self.viewControlLayout.addWidget(self.xyzGroupBox,2,2,3,1)
        
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
        self.levelsPlot = self.levelsPlotItem.plot(np.zeros(256))
        self.lowLevelLine = pg.InfiniteLine(pos=0,pen='r',movable=True,bounds=(0,254))
        self.lowLevelLine.sigPositionChangeFinished.connect(self.lowLevelLineCallback)
        self.levelsPlotItem.addItem(self.lowLevelLine)
        self.highLevelLine = pg.InfiniteLine(pos=255,pen='r',movable=True,bounds=(1,255))
        self.highLevelLine.sigPositionChangeFinished.connect(self.highLevelLineCallback)
        self.levelsPlotItem.addItem(self.highLevelLine)
        
        # levels control
        self.resetLevelsButton = QtGui.QPushButton('Reset Levels')
        self.resetLevelsButton.clicked.connect(self.resetLevelsButtonCallback)        
        
        self.gammaEditLayout = QtGui.QFormLayout()
        self.gammaEdit = QtGui.QLineEdit('')
        self.gammaEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.gammaEdit.editingFinished.connect(self.gammaEditCallback)
        self.gammaEditLayout.addRow('Gamma:',self.gammaEdit)
        
        self.gammaSlider = QtGui.QSlider()
        self.gammaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.gammaSlider.setRange(5,300)
        self.gammaSlider.setValue(100)
        self.gammaSlider.setSingleStep(1)
        self.gammaSlider.sliderReleased.connect(self.gammaSliderCallback) 
        
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
        
        self.normDisplayCheckbox = QtGui.QCheckBox('Normalize Display')
        self.normDisplayCheckbox.stateChanged.connect(self.normDisplayCheckboxCallback)
        
        self.levelsControlLayout = QtGui.QGridLayout()
        self.levelsControlLayout.addWidget(self.resetLevelsButton,0,1,1,1)
        self.levelsControlLayout.addLayout(self.gammaEditLayout,1,0,1,1)
        self.levelsControlLayout.addWidget(self.gammaSlider,1,1,1,2)
        self.levelsControlLayout.addLayout(self.alphaEditLayout,2,0,1,1)
        self.levelsControlLayout.addWidget(self.alphaSlider,2,1,1,2)
        self.levelsControlLayout.addWidget(self.normDisplayCheckbox,3,1,1,1)
        
        # mark points tab
        
        # warp tab
        
        # main layout
        self.mainWidget = QtGui.QWidget()
        self.mainWin.setCentralWidget(self.mainWidget)
        self.mainLayout = QtGui.QGridLayout()
        setLayoutGridSpacing(self.mainLayout,winHeight,winWidth,4,4)
        self.mainWidget.setLayout(self.mainLayout)
        self.mainLayout.addWidget(self.imageLayout,0,0,4,2)
        self.mainLayout.addLayout(self.fileSelectLayout,0,2,1,2)
        self.mainLayout.addLayout(self.windowChannelLayout,1,2,1,1)
        self.mainLayout.addLayout(self.viewControlLayout,2,2,1,1)
        self.mainLayout.addLayout(self.rangeControlLayout,3,2,1,1)
        self.mainLayout.addWidget(self.levelsPlotWidget,1,3,1,1)
        self.mainLayout.addLayout(self.levelsControlLayout,2,3,1,1)
        self.mainWin.show()
        
    def mainWinResizeCallback(self,event):
        if len(self.imageObjs)>0 and len(self.displayedWindows)>0:
            self.setViewBoxRange(self.displayedWindows)
        
    def mainWinCloseCallback(self,event):
        event.accept()
        
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
        currentImage = self.currentImageNum[self.selectedWindow]
        yRange,xRange,zRange = self.getImageRange()
        for i in range(zRange[0]+1,zRange[1]+1):
            self.currentImageNum[self.selectedWindow] = i
            self.updateImage(self.selectedWindow)
            cv2.imwrite(filePath[:-4]+'_'+str(i)+'.tif',self.image[yRange[0]:yRange[1],xRange[0]:xRange[1],::-1])
        self.currentImageNum[self.selectedWindow] = currentImage
                   
    def openFile(self):
        filePaths,fileType = QtGui.QFileDialog.getOpenFileNamesAndFilter(self.mainWin,'Choose File(s)',self.fileOpenPath,'Images (*.tif *.jpg *.png);;Image Series (*.tif *.jpg *.png);;Bruker Dir (*.xml);;Bruker Dir + Siblings (*.xml);;Numpy Array (*npy);;Allen Atlas (*.nrrd)',self.fileOpenType)
        if len(filePaths)<1:
            return
        self.fileOpenPath = os.path.dirname(filePaths[0])
        self.fileOpenType = fileType
        numCh = chFileOrg = None
        if fileType=='Image Series (*.tif *.jpg *.png)':
            filePaths = [filePaths]
            numCh,ok = QtGui.QInputDialog.getInt(self.mainWin,'Import Image Series','Number of channels:',1,min=1)
            if not ok:
                return
            if numCh>1:
                chFileOrg,ok = QtGui.QInputDialog.getItem(self.mainWin,'Import Image Series','Channel file organization:',('alternating','blocks'))
                if not ok:
                    return
        elif fileType=='Bruker Dir + Siblings (*.xml)':
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
            self.imageObjs.append(ImageObj(filePath,fileType,numCh,chFileOrg))
            if isinstance(filePath,list):
                self.fileListbox.addItem(filePath[0])
            else:
                self.fileListbox.addItem(filePath)
            if len(self.imageObjs)>1:
                self.fileListbox.item(self.fileListbox.count()-1).setCheckState(QtCore.Qt.Unchecked)
            else:
                self.fileListbox.item(self.fileListbox.count()-1).setCheckState(QtCore.Qt.Checked)
                self.fileListbox.blockSignals(True)
                self.fileListbox.setCurrentRow(0)
                self.fileListbox.blockSignals(False)
                self.selectedFileIndex = [0]
                self.checkedFileIndex = [[] for _ in range(4)]
                self.checkedFileIndex[0].append(0)
                self.selectedWindow = 0
                self.displayedWindows = [0]
                self.selectedChannelIndex = [[] for _ in range(4)]
                self.currentImageNum = ['' for _ in range(4)]
                self.sliceProjState = [0 for _ in range(4)]
                self.xyzState = [2 for _ in range(4)]
                self.imageShapeIndex = [(0,1,2) for _ in range(4)]
                self.normState = [False for _ in range(4)]
                self.stitchState = [False for _ in range(4)]
                self.selectedAtlasRegions = [[] for _ in range(4)]
                self.initImageWindow()
        if self.stitchCheckbox.isChecked():
            self.stitchPos = np.concatenate((self.stitchPos,np.full((4,len(filePaths),3),np.nan)),axis=1)
        
    def initImageWindow(self):
        self.selectedChannelIndex[self.selectedWindow] = [0]
        self.currentImageNum[self.selectedWindow] = 1 
        self.displayImageInfo()
        self.setViewBoxRangeLimits()
        self.setViewBoxRange(self.displayedWindows)
        self.displayImage()
        
    def resetImageWindow(self):
        if self.stitchCheckbox.isChecked():
            self.stitchCheckbox.setChecked(False)
        self.currentImageNum[self.selectedWindow] = ''
        self.displayedWindows.remove(self.selectedWindow)
        self.displayImageInfo()
        self.setViewBoxRange(self.displayedWindows)
        self.imageItem[self.selectedWindow].setImage(np.zeros((2,2,3),dtype=np.uint8).transpose((1,0,2)),autoLevels=False)
        self.imageViewBox[self.selectedWindow].setMouseEnabled(x=False,y=False)
        
    def displayImageInfo(self):
        self.updateChannelList()
        imgNum = str(self.currentImageNum[self.selectedWindow]) if self.sliceButton.isChecked() else ''
        self.imageNumEdit.setText(imgNum)
        self.displayImageRange()
        self.displayPixelSize()
        self.displayImageLevels()
        
    def displayImageRange(self):
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            if self.stitchCheckbox.isChecked():
                shape = self.stitchShape[self.selectedWindow]
                rng = self.stitchRange[self.selectedWindow]
            else:
                imageObj = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]]
                shape = imageObj.data.shape
                rng = imageObj.range
            self.imageDimensionsLabel.setText('XYZ Dimensions: '+str(shape[1])+', '+str(shape[0])+', '+str(shape[2]))
            self.xRangeLowEdit.setText(str(rng[1][0]+1))
            self.xRangeHighEdit.setText(str(rng[1][1]))
            self.yRangeLowEdit.setText(str(rng[0][0]+1))
            self.yRangeHighEdit.setText(str(rng[0][1]))
            self.zRangeLowEdit.setText(str(rng[2][0]+1))
            self.zRangeHighEdit.setText(str(rng[2][1]))
        else:
            self.imagePixelSizeLabel.setText('XYZ Dimensions: ')
            self.xRangeLowEdit.setText('')
            self.xRangeHighEdit.setText('')
            self.yRangeLowEdit.setText('')
            self.yRangeHighEdit.setText('')
            self.zRangeLowEdit.setText('')
            self.zRangeHighEdit.setText('')
        
    def displayPixelSize(self):
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            pixelSize = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].pixelSize
            self.imagePixelSizeLabel.setText(u'XYZ Pixel Size (\u03BCm): '+str(pixelSize[1])+', '+str(pixelSize[0])+', '+str(pixelSize[2]))
        else:
            self.imagePixelSizeLabel.setText(u'XYZ Pixel Size (\u03BCm): ')
            
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
    
    def displayImageLevels(self):
        fileInd = list(set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex))
        if len(fileInd)>0:
            isSet = False
            pixIntensityHist = np.zeros(256)
            for i in fileInd:
                chInd = [ch for ch in self.selectedChannelIndex[self.selectedWindow] if ch<self.imageObjs[i].data.shape[3]]
                if len(chInd)>0:
                    hist,_ = np.histogram(self.imageObjs[i].data[:,:,:,chInd],bins=256,range=(0,256))
                    pixIntensityHist += hist
                    if not isSet:
                        self.lowLevelLine.setValue(self.imageObjs[i].levels[chInd[0]][0])
                        self.highLevelLine.setValue(self.imageObjs[i].levels[chInd[0]][1])
                        self.gammaEdit.setText(str(self.imageObjs[i].gamma[chInd[0]]))
                        self.gammaSlider.setValue(self.imageObjs[i].gamma[chInd[0]]*100)
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
            self.gammaEdit.setText('')
            self.gammaSlider.setValue(100)
            self.alphaEdit.setText('')
            self.alphaSlider.setValue(100)
            self.levelsPlot.setData(np.zeros(256))
            self.levelsPlotItem.setYRange(0,1)
            self.levelsPlotItem.getAxis('left').setTicks([[(0,'0'),(1,'1')],[]])   
            
    def setViewBoxRangeLimits(self,windows=None):
        if windows is None:
            windows = [self.selectedWindow]
        self.ignoreImageRangeChange = True
        for window in windows:
            imageShape = self.stitchShape[window] if self.stitchState[window] else self.imageObjs[self.checkedFileIndex[window][0]].data.shape
            ymax,xmax = [imageShape[i] for i in self.imageShapeIndex[window][:2]]
            self.imageViewBox[window].setLimits(xMin=0,xMax=xmax,yMin=0,yMax=ymax,minXRange=3,maxXRange=xmax,minYRange=3,maxYRange=ymax)
        self.ignoreImageRangeChange = False
        
    def setViewBoxRange(self,windows=None):
        # square viewBox rectangle to fill layout (or subregion if displaying mulitple image windows)
        # adjust aspect to match image ranged
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
            height = width
        self.ignoreImageRangeChange = True
        for window in windows:
            x,y,w,h = left,top,width,height
            if len(self.displayedWindows)>1:
                w /= 2
                h /= 2
                position = self.displayedWindows.index(window)
                if len(self.displayedWindows)<3:
                    x += w/2   
                elif position in (2,3):
                    x += w
                if position in (1,3):
                    y += h
            yRange,xRange,_ = self.getImageRange(window)
            aspect = (xRange[1]-xRange[0])/(yRange[1]-yRange[0])
            if aspect>1:
                h = w/aspect
                y += (w-h)/2
            else:
                w = h*aspect
                x += (h-w)/2
            x,y,w,h = (int(round(n)) for n in (x,y,w,h))
            self.imageViewBox[window].setGeometry(x,y,w,h)
            self.imageViewBox[window].setRange(xRange=xRange,yRange=yRange,padding=0)
        self.ignoreImageRangeChange = False
        
    def getImageRange(self,window=None):
        if window is None:
            window = self.selectedWindow
        imageRange = self.stitchRange[self.selectedWindow] if self.stitchState[window] else self.imageObjs[self.checkedFileIndex[window][0]].range
        return [imageRange[i] for i in self.imageShapeIndex[window]]
        
    def flipImageHorz(self):
        for fileInd in self.selectedFileIndex:
            self.imageObjs[fileInd].flipHorz()
        self.displayImage(self.getAffectedWindows())
            
    def flipImageVert(self):
        for fileInd in self.selectedFileIndex:
            self.imageObjs[fileInd].flipVert()
        self.displayImage(self.getAffectedWindows())
        
    def rotateImage90(self):
        for window in self.displayedWindows:
            selected = [True if i in self.selectedFileIndex else False for i in self.checkedFileIndex[window]]
            if (self.linkWindowsCheckbox.isChecked() or any(selected)) and not all(selected):
                return      
        for fileInd in self.selectedFileIndex:
            self.imageObjs[fileInd].rotate90()
        affectedWindows = self.getAffectedWindows()
        if self.stitchCheckbox.isChecked():
            self.updateStitchShape(affectedWindows)
        else:
            self.displayImageRange()
            self.setViewBoxRangeLimits(affectedWindows)
            self.setViewBoxRange(affectedWindows)
        self.displayImage(affectedWindows)
        
    def displayImage(self,windows=None,update=True):
        if windows is None:
            windows = [self.selectedWindow]
        for window in windows:
            if update:
                self.updateImage(window)
            self.imageItem[window].setImage(self.image.transpose((1,0,2)),autoLevels=False)
        
    def updateImage(self,window):
        if self.stitchCheckbox.isChecked():
            imageShape = [self.stitchShape[window][i] for i in self.imageShapeIndex[window][:2]]
        else:
            imageShape = [self.imageObjs[self.checkedFileIndex[window][0]].data.shape[i] for i in self.imageShapeIndex[window][:2]]
        rgb = np.zeros((imageShape[0],imageShape[1],3))
        for fileInd in self.checkedFileIndex[window]:
            imageObj = self.imageObjs[fileInd]
            if self.stitchCheckbox.isChecked():
                i,j = [slice(self.stitchPos[window,fileInd,i],self.stitchPos[window,fileInd,i]+imageObj.data.shape[i]) for i in self.imageShapeIndex[window][:2]]
            else:
                i,j = [slice(0,imageObj.data.shape[i]) for i in self.imageShapeIndex[window][:2]]
            for ch in self.selectedChannelIndex[window]:
                if ch<imageObj.data.shape[3]:
                    channelData = self.getChannelData(imageObj,fileInd,window,ch)
                    if channelData is not None:
                        if imageObj.gamma[ch]!=1:
                            channelData /= 255
                            channelData **= imageObj.gamma[ch]
                            channelData *= 255
                        for k in imageObj.rgbInd[ch]:
                            if self.stitchCheckbox.isChecked():
                                rgb[i,j,k] = np.maximum(rgb[i,j,k],channelData)
                            elif imageObj.alpha[ch]<1:
                                rgb[i,j,k] *= 1-imageObj.alpha[ch]
                                rgb[i,j,k] += channelData*imageObj.alpha[ch]
                            else:
                                rgb[i,j,k] = channelData
        if self.normState[window]:
            rgb -= rgb.min()
            rgb[rgb<0] = 0
            if rgb.any():
                rgb *= 255/rgb.max()
        self.image = rgb.astype(np.uint8)
        for regionInd in self.selectedAtlasRegions[window]:
            _,contours,_ = cv2.findContours(self.getAtlasRegion(window,self.atlasRegionIDs[regionInd],imageObj.range).copy(order='C').astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(self.image,contours,-1,(255,255,255))
                    
    def getChannelData(self,imageObj,fileInd,window,ch):
        isSlice = True if self.sliceProjState[window]==0 else False
        if isSlice:
            i = self.currentImageNum[window]-1
            if self.stitchState[window]:
                i -= self.stitchPos[window,fileInd][self.imageShapeIndex[window][2]]
                if not 0<=i<imageObj.data.shape[self.imageShapeIndex[window][2]]:
                    return
        if self.xyzState[window]==2:
            if isSlice:
                channelData = imageObj.data[:,:,i,ch]
            else:
                if self.stitchCheckbox.isChecked():
                    channelData = imageObj.data[:,:,:,ch].max(axis=2)
                else:
                    channelData = imageObj.data[:,:,imageObj.range[2][0]:imageObj.range[2][1],ch].max(axis=2)
        elif self.xyzState[window]==1:
            if isSlice:
                channelData = imageObj.data[i,:,:,ch].T
            else:
                if self.stitchState[window]:
                    channelData = imageObj.data[:,:,:,ch].max(axis=0).T
                else:
                    channelData = imageObj.data[imageObj.range[0][0]:imageObj.range[0][1],:,:,ch].max(axis=0).T
        else:
            if isSlice:
                channelData = imageObj.data[:,i,:,ch]
            else:
                if self.stitchState[window]:
                    channelData = imageObj.data[:,:,:,ch].max(axis=1)
                else:
                    channelData = imageObj.data[:,imageObj.range[1][0]:imageObj.range[1][1],:,ch].max(axis=1)
        channelData = channelData.astype(float)
        if imageObj.levels[ch][0]>0 or imageObj.levels[ch][1]<255:
            channelData -= imageObj.levels[ch][0] 
            channelData[channelData<0] = 0
            channelData *= 255/(imageObj.levels[ch][1]-imageObj.levels[ch][0])
            channelData[channelData>255] = 255
        return channelData
        
    def getAtlasRegion(self,window,region,rng):
        isSlice = True if self.sliceProjState[window]==0 else False
        i = self.currentImageNum[window]-1
        if self.xyzState[window]==2:
            if isSlice:
                a = self.atlasAnnotationData[:,:,i]
                a = np.in1d(a,region).reshape(a.shape)
            else:
                a = self.atlasAnnotationData[:,:,rng[2][0]:rng[2][1]]
                a = np.in1d(a,region).reshape(a.shape).max(axis=2)
        elif self.xyzState[window]==1:
            if isSlice:
                a = self.atlasAnnotationData[i,:,:].T
                a = np.in1d(a,region).reshape(a.shape)
            else:
                a = self.atlasAnnotationData[rng[0][0]:rng[0][1],:,:]
                a = np.in1d(a,region).reshape(a.shape).max(axis=0).T
        else:
            if isSlice:
                a = self.atlasAnnotationData[:,i,:]
                a = np.in1d(a,region).reshape(a.shape)
            else:
                a = self.atlasAnnotationData[:,rng[1][0]:rng[1][1],:]
                a = np.in1d(a,region).reshape(a.shape).max(axis=1)
        return a
        
    def setAtlasRegions(self):
        if self.atlasAnnotationData is None:
            filePath = QtGui.QFileDialog.getOpenFileName(self.mainWin,'Choose Annotation File',self.fileOpenPath,'*.nrrd')
            if filePath=='':
                for region in self.atlasRegionMenu:
                    if region.isChecked():
                        region.setChecked(False)
                return
            self.fileSavePath = os.path.dirname(filePath)
            self.atlasAnnotationData,_ = nrrd.read(filePath)
            self.atlasAnnotationData = self.atlasAnnotationData.transpose((1,2,0))
        self.selectedAtlasRegions[self.selectedWindow] = []
        for ind,region in enumerate(self.atlasRegionMenu):
            if region.isChecked():
                self.selectedAtlasRegions[self.selectedWindow].append(ind)
        self.displayImage()
        
    def clearAtlasRegions(self):
        if len(self.selectedAtlasRegions[self.selectedWindow])>0:
            for region in self.atlasRegionMenu:
                if region.isChecked():
                    region.setChecked(False)
            self.selectedAtlasRegions[self.selectedWindow] = []
            self.displayImage()
        
    def mainWinKeyPressCallback(self,event):
        key = event.key()
        modifiers = QtGui.QApplication.keyboardModifiers()
        if key==44 and self.sliceButton.isChecked(): # <
            self.setImageNum(self.currentImageNum[self.selectedWindow]-1)
        elif key==46 and self.sliceButton.isChecked(): # >
            self.setImageNum(self.currentImageNum[self.selectedWindow]+1)
        elif self.stitchCheckbox.isChecked():
            if int(modifiers & QtCore.Qt.ShiftModifier)>0:
                move = 100
            elif int(modifiers & QtCore.Qt.ControlModifier)>0:
                move = 10
            else:
                move = 1
            fileInd = list(set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex))
            if key==16777235: # up
                self.stitchPos[self.selectedWindow,fileInd,0] -= move
            elif key==16777237: # down
                self.stitchPos[self.selectedWindow,fileInd,0] += move
            elif key==16777234: # left
                self.stitchPos[self.selectedWindow,fileInd,1] -= move
            elif key==16777236: # right
                self.stitchPos[self.selectedWindow,fileInd,1] += move
            elif key==61: # plus
                self.stitchPos[self.selectedWindow,fileInd,2] -= move
            elif key==45: # minus
                self.stitchPos[self.selectedWindow,fileInd,2] += move
            else:
                return
            self.updateStitchShape()
            self.displayImage()
        
    def fileListboxSelectionCallback(self):
        self.selectedFileIndex = getSelectedItemsIndex(self.fileListbox)
        self.displayImageLevels()
        
    def fileListboxItemClickedCallback(self,item):
        fileInd = self.fileListbox.indexFromItem(item).row()
        checked = self.checkedFileIndex[self.selectedWindow]
        if item.checkState()==QtCore.Qt.Checked and fileInd not in checked:
            if not self.stitchCheckbox.isChecked() and len(checked)>0 and self.imageObjs[fileInd].data.shape[:3]!=self.imageObjs[checked[0]].data.shape[:3]:
                item.setCheckState(QtCore.Qt.Unchecked)
            else:
                checked.append(fileInd)
                checked.sort()
                if len(checked)>1:
                    if self.imageObjs[fileInd].data.shape[3]>self.channelListbox.count():
                        self.updateChannelList()
                else:
                    self.displayedWindows.append(self.selectedWindow)
                    self.displayedWindows.sort()
                if self.stitchCheckbox.isChecked():
                    self.stitchPos[self.selectedWindow,fileInd,:] = 0
                    self.updateStitchShape()
                    self.displayImageLevels()
                    self.displayImage()
                else:
                    if len(checked)>1:
                        self.imageObjs[fileInd].range = self.imageObjs[checked[0]].range[:]
                        self.displayImageLevels()
                        self.displayImage()
                    else:
                        self.initImageWindow()
        else:
            if fileInd in checked:
                checked.remove(fileInd)
                if len(checked)<1:
                    self.resetImageWindow()
                elif self.stitchCheckbox.isChecked():
                    self.stitchPos[self.selectedWindow,fileInd,:] = np.nan
                    self.updateStitchShape()
                    self.displayImageLevels()
                    self.displayImage()                    
                    
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
        self.displayImage(self.getAffectedWindows())
    
    def removeFileButtonCallback(self):
        affectedWindows = self.getAffectedWindows()
        if self.stitchCheckbox.isChecked():
            self.stitchPos = np.delete(self.stitchPos,self.selectedFileIndex,axis=1)
        for fileInd in reversed(self.selectedFileIndex):
            for checked in self.checkedFileIndex:
                if fileInd in checked:
                    checked.remove(fileInd)
            self.imageObjs.remove(self.imageObjs[fileInd])
            self.fileListbox.takeItem(fileInd)
        self.selectedFileIndex = []
        if len(self.checkedFileIndex[self.selectedWindow])<1:
            self.resetImageWindow()
        else:
            self.updateChannelList()
            self.displayImageLevels()
            self.displayImage(affectedWindows)
            
    def stitchCheckboxCallback(self):
        if self.stitchCheckbox.isChecked():
            if self.linkCheckebox.isChecked():
                self.stitchCheckbox.setChecked(False)
            else:
                self.stitchState[self.selectedWindow] = True
                for i in range(self.fileListbox.count()):
                    if i in self.selectedFileIndex:
                        self.fileListbox.item(i).setCheckState(QtCore.Qt.Checked)
                    else:
                        self.fileListbox.item(i).setCheckState(QtCore.Qt.Unchecked)
                self.checkedFileIndex = self.selectedFileIndex[:]
                self.stitchPos = np.full((4,self.fileListbox.count(),3),np.nan)
                useStagePos = all([self.imageObjs[i].position is not None for i in self.selectedFileIndex])
                col = 0
                pos = [0,0,0]
                for i in self.selectedFileIndex:
                    if useStagePos:
                        self.stitchPos[self.selectedWindow,i,:] = self.imageObjs[i].position
                    else:
                        if col>math.floor(len(self.selectedFileIndex)**0.5):
                            col = 0
                            pos[0] += self.imageObjs[i].data.shape[0]
                            pos[1] = 0
                        elif col>0:
                            pos[1] += self.imageObjs[i].data.shape[1]
                        col += 1
                        self.stitchPos[self.selectedWindow,i,:] = pos
                self.stitchShape = [None for _ in range(4)]
                self.stitchRange = [[] for _ in range(4)]
                self.holdStitchRange = False
                self.updateStitchShape()
                self.displayImageLevels()
                self.displayImage()
        else:
            self.stitchState[self.selectedWindow] = True
            for i in self.checkedFileIndex[self.selectedWindow][1:]:
                self.fileListbox.item(i).setCheckState(QtCore.Qt.Unchecked)
            for window in self.displayedWindows:
                del(self.checkedFileIndex[self.selectedWindow][1:])
            self.initImageWindow()
    
    def updateStitchShape(self,windows=None):
        if windows is None:
            windows = [self.selectedWindow]
        for window in windows:
            self.stitchPos[window] -= np.nanmin(self.stitchPos[window],axis=0)
            imageShapes = np.array([self.imageObjs[i].data.shape[0:3] for i in self.checkedFileIndex[window]])
            self.stitchShape[window] = (self.stitchPos[self.selectedWindow,self.checkedFileIndex[window],:]+imageShapes).max(axis=0)
            if self.holdStitchRange:
                for i in (0,1,2):
                    if self.stitchRange[window][i][1]>self.stitchShape[window][i]:
                        self.stitchRange[window][i][1] = self.stitchShape[window][i]
            else:
                self.stitchRange[window] = [[0,self.stitchShape[window][i]] for i in (0,1,2)]
        self.setViewBoxRangeLimits(windows)
        self.setViewBoxRange(windows)
        self.displayImageRange()
        
    def viewChannelsCheckboxCallback(self):
        pass
    
    def view3DCheckboxCallback(self):
        pass
        
    def getAffectedWindows(self,chInd=None):
        if chInd is not None:
            chInd = self.selectedChannelIndex[self.selectedWindow]
        return [window for window in self.displayedWindows if any(i in self.selectedFileIndex for i in self.checkedFileIndex[window]) and (chInd is None or any(ch in chInd for ch in self.selectedChannelIndex[window]))]
            
    def windowListboxCallback(self):
        self.selectedWindow = getSelectedItemsIndex(self.windowListbox)[0]
        for i in range(self.fileListbox.count()):
            if i in self.checkedFileIndex[self.selectedWindow]:
                self.fileListbox.item(i).setCheckState(QtCore.Qt.Checked)
            else:
                self.fileListbox.item(i).setCheckState(QtCore.Qt.Unchecked)
        self.sliceProjButtons[self.sliceProjState[self.selectedWindow]].setChecked(True)
        self.xyzButtons[self.xyzState[self.selectedWindow]].setChecked(True)
        self.stitchCheckbox.setChecked(self.stitchState[self.selectedWindow])
        for ind,region in enumerate(self.atlasRegionMenu):
            region.setChecked(ind in self.selectedAtlasRegions[self.selectedWindow])
        self.displayImageInfo()
    
    def linkWindowsCheckboxCallback(self):
        if self.linkWindowsCheckbox.isChecked():
            if self.stitchCheckbox.isChecked():
                self.linkWindowsCheckbox.setChecked(False)
            elif len(self.displayedWindows)>1:
                imageObj = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]]
                otherWindows = self.displayedWindows[:]
                otherWindows.remove(self.selectedWindow)
                if any(self.imageObjs[self.checkedFileIndex[window][0]].data.shape[:3]!=imageObj.data.shape[:3] for window in otherWindows):
                    return
                else:
                    for window in otherWindows:
                        for i in self.checkedFileIndex[window]:
                            self.imageObjs[i].range = imageObj.range[:]
                self.setViewBoxRange()
                self.displayImage()
        
    def channelListboxCallback(self):
        self.selectedChannelIndex[self.selectedWindow] = getSelectedItemsIndex(self.channelListbox)
        self.displayImageLevels()
        self.displayImage()
        
    def updateChannelList(self):
        self.channelListbox.blockSignals(True)
        self.channelListbox.clear()
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            numCh = max(self.imageObjs[i].data.shape[3] for i in self.checkedFileIndex[self.selectedWindow])
            for ch in range(numCh):
                item = QtGui.QListWidgetItem('Ch'+str(ch),self.channelListbox)
                if ch in self.selectedChannelIndex[self.selectedWindow]:
                    item.setSelected(True)
        self.channelListbox.blockSignals(False)
        
    def channelColorMenuCallback(self):
        color = self.channelColorMenu.currentText()
        self.channelColorMenu.setCurrentIndex(0)
        if color!='Channel Color':
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
                for ch in self.selectedChannelIndex[self.selectedWindow]:
                    if ch<self.imageObjs[fileInd].data.shape[3]:
                        self.imageObjs[fileInd].rgbInd[ch] = rgbInd
            self.displayImage(self.getAffectedWindows(chInd=True))
        
    def imageNumEditCallback(self):
        self.setImageNum(int(self.imageNumEdit.text()))
        
    def setImageNum(self,imageNum):
        imageShape = self.stitchShape[self.selectedWindow] if self.stitchCheckbox.isChecked() else self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].data.shape
        if imageNum<1:
            imageNum = 1
        elif imageNum>imageShape[self.imageShapeIndex[self.selectedWindow][2]]:
            imageNum = imageShape[self.imageShapeIndex[self.selectedWindow][2]]
        self.imageNumEdit.setText(str(imageNum))
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.currentImageNum[window] = imageNum
        self.displayImage(windows)
        
    def sliceProjButtonCallback(self):
        if self.sliceButton.isChecked():
            self.imageNumEdit.setEnabled(True)
            self.imageNumEdit.setText(str(self.currentImageNum[self.selectedWindow]))
            state = 0
        else:
            self.imageNumEdit.setEnabled(False)
            self.imageNumEdit.setText('')
            state = 1
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.sliceProjState[window] = state
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
            self.sliceProjState[window] = state
            self.imageShapeIndex[window] = shapeInd
            self.currentImageNum[window] = 1
        if self.sliceButton.isChecked():
            self.imageNumEdit.setText('1')
        self.setViewBoxRangeLimits(windows)
        self.setViewBoxRange(windows)
        self.displayImage(windows)
        
    def zoomPanButtonCallback(self):
        isOn = self.zoomPanButton.isChecked()
        for window in self.displayedWindows:
            self.imageViewBox[window].setMouseEnabled(x=isOn,y=isOn)
        
    def resetViewButtonCallback(self):
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        if self.stitchCheckbox.isChecked():
            shape = self.stitchShape[self.selectedWindow]
            self.stitchRange[self.selectedWindow] = [[0,shape[i]] for i in (0,1,2)]
            self.holdStitchRange = False
        else:
            shape = self.imageObjs[self.checkedFileIndex[self.selectedWindow]].data.shape
            for fileInd in (set().union(*(self.checkedFileIndex[window] for window in windows)) | set(self.selectedFileIndex)):
                self.imageObjs[fileInd].range = [[0,shape[i]] for i in (0,1,2)]
        self.xRangeLowEdit.setText('1')
        self.xRangeHighEdit.setText(str(shape[1]))
        self.yRangeLowEdit.setText('1')
        self.yRangeHighEdit.setText(str(shape[0]))
        self.zRangeLowEdit.setText('1')
        self.zRangeHighEdit.setText(str(shape[2]))
        self.setViewBoxRange()
        if self.projectionButton.isChecked():
            self.displayImage(windows)
        
    def xRangeLowEditCallback(self):
        self.updateImageRange('low',self.xRangeLowEdit,self.xRangeHighEdit,self.xButton,axisInd=1)
            
    def xRangeHighEditCallback(self):
        self.updateImageRange('high',self.xRangeLowEdit,self.xRangeHighEdit,self.xButton,axisInd=1)
        
    def yRangeLowEditCallback(self):
        self.updateImageRange('low',self.yRangeLowEdit,self.yRangeHighEdit,self.yButton,axisInd=0)
            
    def yRangeHighEditCallback(self):
        self.updateImageRange('high',self.yRangeLowEdit,self.yRangeHighEdit,self.yButton,axisInd=0)
        
    def zRangeLowEditCallback(self):
        self.updateImageRange('low',self.zRangeLowEdit,self.zRangeHighEdit,self.zButton,axisInd=2)
            
    def zRangeHighEditCallback(self):
        self.updateImageRange('high',self.zRangeLowEdit,self.zRangeHighEdit,self.zButton,axisInd=2)
            
    def updateImageRange(self,lowHigh,lowEdit,highEdit,axisButton,axisInd):
        if lowHigh=='low':
            newVal = int(lowEdit.text())
            axMax = int(highEdit.text())
            if newVal<1:
                newVal = 1
            elif newVal>=axMax-1:
                newVal = axMax-1
            lowEdit.setText(str(newVal))
            rangeInd = 0
        else:
            newVal = int(highEdit.text())
            axMin = int(lowEdit.text())
            axMax = self.stitchShape[self.selectedWindow][axisInd] if self.stitchCheckbox.isChecked() else self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].data.shape[axisInd]
            if newVal<=axMin:
                newVal = axMin+1
            elif newVal>axMax:
                newVal = axMax
            highEdit.setText(str(newVal))
            rangeInd = 1
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        if self.stitchCheckbox.isChecked():
            self.setImageRange(self.stitchRange[self.selectedWindow],self.stitchShape[self.selectedWindow],newVal,axisInd,rangeInd)
            self.holdStitchRange = True
        else:
            for fileInd in set().union(*(self.checkedFileIndex[window] for window in windows)):
                self.setImageRange(self.imageObjs[fileInd].range,self.imageObjs[fileInd].data.shape,newVal,axisInd,rangeInd)
        if axisButton.isChecked:
            if self.projectionButton.isChecked():
                self.displayImage(windows)
        else:
            self.setViewBoxRange(windows)
        
    def imageRangeChanged(self):
        if len(self.imageObjs)<1 or self.ignoreImageRangeChange:
            return
        newRange = [[int(round(n)) for n in x] for x in reversed(self.imageViewBox[self.selectedWindow].viewRange())]
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
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        if self.stitchCheckbox.isChecked():
            self.setImageRange(self.stitchRange[self.selectedWindow],self.stitchShape[self.selectedWindow],newRange,self.imageShapeIndex[self.selectedWindow][:2])
            self.holdStitchRange = True
        else:
            for fileInd in set().union(*(self.checkedFileIndex[window] for window in windows)):
                self.setImageRange(self.imageObjs[fileInd].range,self.imageObjs[fileInd].data.shape,newRange,self.imageShapeIndex[self.selectedWindow][:2])
        self.setViewBoxRange(windows)
        
    def setImageRange(self,imageRange,imageShape,newVal,axes=(0,1,2),rangeInd=None):
        if rangeInd is None:
            newRange = newVal
        else:
            newRange = imageRange[:]
            newRange[rangeInd] = newVal
        for ax,rng in zip(axes,newRange):
            if rng[0]<0:
                rng[0] = 0
            if rng[1]>imageShape[ax]:
                rng[1] = imageShape[ax]
            imageRange[ax] = rng
        
    def saveImageRange(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.p')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        rng = [[int(self.yRangeLowEdit.text())-1,int(self.yRangeHighEdit.text())],[int(self.xRangeLowEdit.text())-1,int(self.xRangeHighEdit.text())],[int(self.zRangeLowEdit.text())-1,int(self.zRangeHighEdit.text())]]
        np.save(filePath,rng)
    
    def loadImageRange(self):
        filePath = QtGui.QFileDialog.getOpenFileName(self.mainWin,'Choose File',self.fileOpenPath,'*.p')
        if filePath=='':
            return
        self.fileOpenPath = os.path.dirname(filePath)
        rng = np.load(filePath)
        self.xRangeLowEdit.setText(str(rng[1][0]+1))
        self.xRangeHighEdit.setText(str(rng[1][1]))
        self.yRangeLowEdit.setText(str(rng[0][0]+1))
        self.yRangeHighEdit.setText(str(rng[0][1]))
        self.zRangeLowEdit.setText(str(rng[2][0]+1))
        self.zRangeHighEdit.setText(str(rng[2][1]))
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        if self.stitchCheckbox.isChecked():
            self.setImageRange(self.stitchRange[self.selectedWindow],self.stitchShape[self.selectedWindow],rng)
            self.holdStitchRange = True
        else:
            for fileInd in set().union(*(self.checkedFileIndex[window] for window in windows)):
                self.setImageRange(self.imageObjs[fileInd].range,self.imageObjs[fileInd].data.shape,rng)
        self.setViewBoxRange(windows)
        
    def lowLevelLineCallback(self):
        newVal = self.lowLevelLine.value()
        #self.highLevelLine.setBounds((newVal+1,255))
        self.setLevels(newVal,levelsInd=0)
         
    def highLevelLineCallback(self):
        newVal = self.highLevelLine.value()
        #self.lowLevelLine.setBounds((0,newVal-1))
        self.setLevels(newVal,levelsInd=1)
        
    def setLevels(self,newVal,levelsInd):
        for fileInd in self.selectedFileIndex:
            for ch in self.selectedChannelIndex[self.selectedWindow]:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].levels[ch][levelsInd] = newVal
        self.displayImage(self.getAffectedWindows(chInd=True))
        
    def gammaEditCallback(self):
        newVal = round(float(self.gammaEdit.text()),2)
        if newVal<0.05:
            newVal = 0.05
        elif newVal>3:
            newVal = 3
        self.gammaEdit.setText(str(newVal))
        self.gammaSlider.setValue(newVal*100)
        self.setGamma(newVal)
    
    def gammaSliderCallback(self):
        newVal = self.gammaSlider.value()/100
        self.gammaEdit.setText(str(newVal))
        self.setGamma(newVal)
    
    def setGamma(self,newVal):
        for fileInd in self.selectedFileIndex:
            for ch in self.selectedChannelIndex[self.selectedWindow]:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].gamma[ch] = newVal
        self.displayImage(self.getAffectedWindows(chInd=True))
        
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
        
    def setAlpha(self,newVal):
        for fileInd in self.selectedFileIndex:
            for ch in self.selectedChannelIndex[self.selectedWindow]:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].alpha[ch] = newVal
        self.displayImage(self.getAffectedWindows(chInd=True))
        
    def normDisplayCheckboxCallback(self):
        self.normState[self.selectedWindow] = not self.normState(self.selectedWindow)
        self.displayImage()
        
    def resetLevelsButtonCallback(self):
        self.lowLevelLine.setValue(0)
        self.highLevelLine.setValue(255)
        self.gammaEdit.setText('1')
        self.gammaSlider.setValue(100)
        self.alphaEdit.setText('1')
        self.alphaSlider.setValue(100)
        for fileInd in self.selectedFileIndex:
            for ch in self.selectedChannelIndex[self.selectedWindow]:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].levels[ch] = [0,255]
                    self.imageObjs[fileInd].gamma[ch] = 1
                    self.imageObjs[fileInd].alpha[ch] = 1
        self.displayImage(self.getAffectedWindows(chInd=True))


class ImageObj():
    
    def __init__(self,filePath,fileType,numCh,chFileOrg):
        if fileType=='Images (*.tif *.jpg *.png)':
            self.data = cv2.imread(filePath,cv2.IMREAD_UNCHANGED)
        elif fileType=='Image Series (*.tif *.jpg *.png)':
            if len(filePath)%numCh>0:
                return
            filesPerCh = int(len(filePath)/numCh)
            for ch in range(numCh):
                if chFileOrg=='alternating':
                    chFiles = filePath[ch:len(filePath):numCh]
                else:
                    startFile = ch*filesPerCh
                    chFiles = filePath[startFile:startFile+filesPerCh]
                for ind,f in enumerate(chFiles):
                    d = cv2.imread(f,cv2.IMREAD_UNCHANGED)
                    if ind==0:
                        chData = np.zeros((d.shape+(filesPerCh,)),dtype=d.dtype)
                        chData[:,:,0] = d
                    elif d.shape==chData.shape[:2]:
                        chData[:,:,ind] = d
                    else:
                        return
                if ch==0:
                    self.data = chData[:,:,:,None]
                elif chData.shape[:2]==self.data.shape[:2]:
                    self.data = np.concatenate((self.data,chData[:,:,:,None]),axis=-1)
                else:
                    return
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
        elif fileType=='Allen Atlas (*.nrrd)':
            self.data,_ = nrrd.read(filePath)
            self.data = self.data.transpose((1,2,0))
            self.pixelSize = [25.0]*3
        
        if self.data.dtype!='uint8':
            self.data = make8bit(self.data)
        
        if len(self.data.shape)<3:
            self.data = self.data[:,:,None,None]
        elif len(self.data.shape)<4:
            self.data = self.data[:,:,:,None]
        
        numCh = self.data.shape[3]
        self.range = [[0,self.data.shape[i]] for i in (0,1,2)]
        self.levels = [[0,255] for _ in range(numCh)]
        self.gamma = [1 for _ in range(numCh)]
        self.alpha = [1 for _ in range(numCh)]
        
        if self.data.shape[3]==2:
            self.rgbInd = [(0,2),(1,)]
        elif self.data.shape[3]==3:
            self.rgbInd = [(0,),(1,),(2,)]
        else:
            self.rgbInd = [(0,1,2) for _ in range(numCh)]
        
        if not hasattr(self,'pixelSize'):
            self.pixelSize = [None]*3
        if not hasattr(self,'position'):
            self.position = None
            
    def flipHorz(self):
        self.data = self.data[:,::-1]
            
    def flipVert(self):
        self.data = self.data[::-1]
        
    def rotate90(self):
        self.data = np.rot90(self.data)
        self.range[:2] = self.range[1::-1]
                
                
def make8bit(data):
    data = data.astype(float)
    data *= 255/data.max()
    return data.round().astype(np.uint8)
    
    
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