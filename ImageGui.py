# -*- coding: utf-8 -*-
"""
Image visualization and analysis GUI

@author: samgale
"""

from __future__ import division
import sip
sip.setapi('QString', 2)
import os, time, math, cv2, nrrd
from xml.dom import minidom
import numpy as np
from PyQt4 import QtGui, QtCore
import pyqtgraph as pg


def start(data=None,label=None,mode=None):
    app = QtGui.QApplication.instance()
    if app is None:
        app = QtGui.QApplication([])
    imageGuiObj = ImageGui(app)
    if data is not None:
        app.processEvents()
        imageGuiObj.loadImageData(data,label)
        if mode=='channels':
            imageGuiObj.setViewChannelsOn()
        elif mode=='3D':
            imageGuiObj.setView3dOn()
    app.exec_()


class ImageGui():
    
    def __init__(self,app):
        self.app = app
        self.fileOpenPath = os.path.dirname(os.path.realpath(__file__))
        self.fileOpenType = 'Images (*.tif *.jpg)'
        self.fileSavePath = self.fileOpenPath
        self.imageObjs = []
        self.selectedFileIndex = []
        self.checkedFileIndex = [[] for _ in range(4)]
        self.selectedWindow = 0
        self.displayedWindows = []
        self.selectedChannelIndex = [[] for _ in range(4)]
        self.sliceProjState = [0 for _ in range(4)]
        self.xyzState = [2 for _ in range(4)]
        self.imageShapeIndex = [(0,1,2) for _ in range(4)]
        self.imageRange = [None for _ in range(4)]
        self.imageIndex = [None for _ in range(4)]
        self.normState = [False for _ in range(4)]
        self.stitchState = [False for _ in range(4)]
        self.stitchPos = np.full((4,1,3),np.nan)
        self.stitchShape = [None for _ in range(4)]
        self.holdStitchRange = [False for _ in range(4)]
        self.selectedAtlasRegions = [[] for _ in range(4)]
        
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
        mouseClickCallbacks = (self.window1MouseClickCallback,self.window2MouseClickCallback,self.window3MouseClickCallback,self.window4MouseClickCallback)
        for viewBox,imgItem,clickCallback in zip(self.imageViewBox,self.imageItem,mouseClickCallbacks):
            viewBox.sigRangeChanged.connect(self.imageRangeChanged)
            imgItem.mouseClickEvent = clickCallback
            viewBox.addItem(imgItem)
            self.imageLayout.addItem(viewBox)
        
        self.view3dSliceLines = [[pg.InfiniteLine(pos=0,angle=angle,pen='r',movable=True) for angle in (0,90)] for _ in range(3)]
        for windowLines in self.view3dSliceLines:
            for line in windowLines:
                line.sigDragged.connect(self.view3dSliceLineDragged)
        
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
        
        self.fileSelectLayout = QtGui.QGridLayout()
        self.fileSelectLayout.addWidget(self.moveFileDownButton,0,0,1,1)
        self.fileSelectLayout.addWidget(self.moveFileUpButton,0,1,1,1)
        self.fileSelectLayout.addWidget(self.removeFileButton,0,2,1,2)
        self.fileSelectLayout.addWidget(self.stitchCheckbox,0,8,1,2)
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
        
        self.sliceButton = QtGui.QRadioButton('Slice')
        self.sliceButton.setChecked(True)
        self.projectionButton = QtGui.QRadioButton('Projection')
        self.sliceProjButtons = (self.sliceButton,self.projectionButton)
        for button in self.sliceProjButtons:
            button.clicked.connect(self.sliceProjButtonCallback)
        self.sliceProjGroupLayout = QtGui.QVBoxLayout()
        self.sliceProjGroupLayout.addWidget(self.sliceButton)
        self.sliceProjGroupLayout.addWidget(self.projectionButton)
        self.sliceProjGroupBox = QtGui.QGroupBox()
        self.sliceProjGroupBox.setLayout(self.sliceProjGroupLayout)
        
        self.xButton = QtGui.QRadioButton('X')
        self.yButton = QtGui.QRadioButton('Y')
        self.zButton = QtGui.QRadioButton('Z')
        self.zButton.setChecked(True)
        self.xyzButtons = (self.xButton,self.yButton,self.zButton)
        for button in self.xyzButtons:
            button.clicked.connect(self.xyzButtonCallback)
        self.xyzGroupLayout = QtGui.QVBoxLayout()
        self.xyzGroupLayout.addWidget(self.xButton)
        self.xyzGroupLayout.addWidget(self.yButton)
        self.xyzGroupLayout.addWidget(self.zButton)
        self.xyzGroupBox = QtGui.QGroupBox()
        self.xyzGroupBox.setLayout(self.xyzGroupLayout)
        
        self.viewChannelsCheckbox = QtGui.QCheckBox('Channel View')
        self.viewChannelsCheckbox.stateChanged.connect(self.viewChannelsCheckboxCallback)
        
        self.view3dCheckbox = QtGui.QCheckBox('3D View')
        self.view3dCheckbox.stateChanged.connect(self.view3dCheckboxCallback)
        
        self.viewControlLayout = QtGui.QGridLayout()
        self.viewControlLayout.addWidget(self.imageDimensionsLabel,0,0,1,3)
        self.viewControlLayout.addWidget(self.imagePixelSizeLabel,1,0,1,3)
        self.viewControlLayout.addWidget(self.viewChannelsCheckbox,2,0,1,1)
        self.viewControlLayout.addWidget(self.view3dCheckbox,2,1,1,1)
        self.viewControlLayout.addWidget(self.sliceProjGroupBox,3,0,2,2)
        self.viewControlLayout.addWidget(self.xyzGroupBox,2,2,3,1)
        
        # range control 
        self.zoomPanButton = QtGui.QPushButton('Zoom/Pan',checkable=True)
        self.zoomPanButton.clicked.connect(self.zoomPanButtonCallback)        
        
        self.resetViewButton = QtGui.QPushButton('Reset View')
        self.resetViewButton.clicked.connect(self.resetViewButtonCallback)
        
        self.rangeViewLabel = QtGui.QLabel('View')
        self.rangeMinLabel = QtGui.QLabel('Min')
        self.rangeMaxLabel = QtGui.QLabel('Max')
        for label in (self.rangeViewLabel,self.rangeMinLabel,self.rangeMaxLabel):
            label.setAlignment(QtCore.Qt.AlignHCenter)
        
        self.xRangeLabel = QtGui.QLabel('X')
        self.yRangeLabel = QtGui.QLabel('Y')
        self.zRangeLabel = QtGui.QLabel('Z')
        
        self.xImageNumEdit = QtGui.QLineEdit('')
        self.yImageNumEdit = QtGui.QLineEdit('')
        self.zImageNumEdit = QtGui.QLineEdit('')
        self.imageNumEditBoxes = (self.yImageNumEdit,self.xImageNumEdit,self.zImageNumEdit)
        for editBox in self.imageNumEditBoxes:
            editBox.setAlignment(QtCore.Qt.AlignHCenter)
            editBox.editingFinished.connect(self.imageNumEditCallback)
        
        self.xRangeMinEdit = QtGui.QLineEdit('')
        self.xRangeMaxEdit = QtGui.QLineEdit('')
        self.yRangeMinEdit = QtGui.QLineEdit('')
        self.yRangeMaxEdit = QtGui.QLineEdit('')
        self.zRangeMinEdit = QtGui.QLineEdit('')
        self.zRangeMaxEdit = QtGui.QLineEdit('')
        self.rangeEditBoxes = ((self.yRangeMinEdit,self.yRangeMaxEdit),(self.xRangeMinEdit,self.xRangeMaxEdit),(self.zRangeMinEdit,self.zRangeMaxEdit))
        for editBox in (box for boxes in self.rangeEditBoxes for box in boxes):
            editBox.setAlignment(QtCore.Qt.AlignHCenter)
            editBox.editingFinished.connect(self.rangeEditCallback)
        
        self.rangeControlLayout = QtGui.QGridLayout()
        self.rangeControlLayout.addWidget(self.zoomPanButton,0,0,1,2)
        self.rangeControlLayout.addWidget(self.resetViewButton,0,2,1,2)
        self.rangeControlLayout.addWidget(self.rangeViewLabel,1,1,1,1)
        self.rangeControlLayout.addWidget(self.rangeMinLabel,1,2,1,1)
        self.rangeControlLayout.addWidget(self.rangeMaxLabel,1,3,1,1)
        self.rangeControlLayout.addWidget(self.xRangeLabel,2,0,1,1)
        self.rangeControlLayout.addWidget(self.xImageNumEdit,2,1,1,1)
        self.rangeControlLayout.addWidget(self.xRangeMinEdit,2,2,1,1)
        self.rangeControlLayout.addWidget(self.xRangeMaxEdit,2,3,1,1)
        self.rangeControlLayout.addWidget(self.yRangeLabel,3,0,1,1)
        self.rangeControlLayout.addWidget(self.yImageNumEdit,3,1,1,1)
        self.rangeControlLayout.addWidget(self.yRangeMinEdit,3,2,1,1)
        self.rangeControlLayout.addWidget(self.yRangeMaxEdit,3,3,1,1)
        self.rangeControlLayout.addWidget(self.zRangeLabel,4,0,1,1)
        self.rangeControlLayout.addWidget(self.zImageNumEdit,4,1,1,1)
        self.rangeControlLayout.addWidget(self.zRangeMinEdit,4,2,1,1)
        self.rangeControlLayout.addWidget(self.zRangeMaxEdit,4,3,1,1)
                
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
        
        self.normDisplayCheckbox = QtGui.QCheckBox('Normalize Display')
        self.normDisplayCheckbox.stateChanged.connect(self.normDisplayCheckboxCallback)
        
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
        
        self.levelsControlLayout = QtGui.QGridLayout()
        self.levelsControlLayout.addWidget(self.resetLevelsButton,0,0,1,1)
        self.levelsControlLayout.addWidget(self.normDisplayCheckbox,0,1,1,1)
        self.levelsControlLayout.addLayout(self.gammaEditLayout,1,0,1,1)
        self.levelsControlLayout.addWidget(self.gammaSlider,1,1,1,1)
        self.levelsControlLayout.addLayout(self.alphaEditLayout,2,0,1,1)
        self.levelsControlLayout.addWidget(self.alphaSlider,2,1,1,1)
        
        # mark points tab
        self.utilityTabs = QtGui.QTabWidget()
        self.markPointsTable = QtGui.QTableWidget(1,3)
        self.markPointsTable.setHorizontalHeaderLabels(['X','Y','Z'])
#        for j in range(3):
#            item = QtGui.QTableWidgetItem(str(j))
#            self.markPointsTable.setItem(0,j,item)
        self.markPointsLayout = QtGui.QGridLayout()
        self.markPointsLayout.addWidget(self.markPointsTable,0,0,1,1)
        self.markPointsTab = QtGui.QWidget()
        self.markPointsTab.setLayout(self.markPointsLayout)
        self.utilityTabs.addTab(self.markPointsTab,'Mark Points')
        
        # align/warp tab
        self.warpLayout = QtGui.QGridLayout()
        self.warpTab = QtGui.QWidget()
        self.warpTab.setLayout(self.warpLayout)
        self.utilityTabs.addTab(self.warpTab,'Align/Warp')
        
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
        self.mainLayout.addWidget(self.utilityTabs,3,3,1,1)
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
        yRange,xRange = [self.imageRange[self.selectedWindow][axis] for axis in self.imageShapeIndex[self.selectedWindow][:2]]
        cv2.imwrite(filePath,self.image[yRange[0]:yRange[1],xRange[0]:xRange[1],::-1])
        
    def saveVolume(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.tif')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        imageIndex = self.imageIndex[self.selectedWindow]
        yRange,xRange,zRange = [self.imageRange[self.selectedWindow][axis] for axis in self.imageShapeIndex[self.selectedWindow]]
        for i in range(zRange[0],zRange[1]+1):
            self.imageIndex[self.selectedWindow] = i
            self.updateImage(self.selectedWindow)
            cv2.imwrite(filePath[:-4]+'_'+str(i)+'.tif',self.image[yRange[0]:yRange[1]+1,xRange[0]:xRange[1]+1,::-1])
        self.imageIndex[self.selectedWindow] = imageIndex
                   
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
            self.loadImageData(filePath,fileType,numCh,chFileOrg)
        
    def loadImageData(self,filePath,fileType,numCh=None,chFileOrg=None):
        # filePath and fileType can also be a numpy array (Y x X x Z x Channels) and optional label, respectively
        # Provide numCh and chFileOrg if importing a multiple file image series
        self.imageObjs.append(ImageObj(filePath,fileType,numCh,chFileOrg))
        if isinstance(filePath,np.ndarray):
            label = 'data_'+time.strftime('%Y%m%d_%H%M%S') if fileType is None else fileType
        elif isinstance(filePath,list):
            label = filePath[0]
        else:
            label = fileType
        self.fileListbox.addItem(label)
        if len(self.imageObjs)>1:
            self.fileListbox.item(self.fileListbox.count()-1).setCheckState(QtCore.Qt.Unchecked)
            if self.stitchCheckbox.isChecked():
                self.stitchPos = np.concatenate((self.stitchPos,np.full((4,1,3),np.nan)),axis=1)
        else:
            self.fileListbox.item(self.fileListbox.count()-1).setCheckState(QtCore.Qt.Checked)
            self.fileListbox.blockSignals(True)
            self.fileListbox.setCurrentRow(0)
            self.fileListbox.blockSignals(False)
            self.selectedFileIndex = [0]
            self.checkedFileIndex[self.selectedWindow] = [0]
            self.displayedWindows = [self.selectedWindow]
            self.initImageWindow()
        
    def initImageWindow(self):
        self.selectedChannelIndex[self.selectedWindow] = [0] 
        self.imageRange[self.selectedWindow] = [[0,size-1] for size in self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].data.shape]
        self.imageIndex[self.selectedWindow] = [0,0,0]
        self.displayImageInfo()
        self.setViewBoxRangeLimits()
        self.setViewBoxRange(self.displayedWindows)
        self.displayImage()
        if self.zoomPanButton.isChecked():
            self.imageViewBox[self.selectedWindow].setMouseEnabled(x=True,y=True)
        
    def resetImageWindow(self,window=None):
        if window is None:
            window = self.selectedWindow
        self.sliceProjState[window] = 0
        self.xyzState[window] = 2
        self.imageShapeIndex[window] = (0,1,2)
        self.normState[window] = False
        self.stitchState[window] = False
        self.selectedAtlasRegions[window] = []
        self.displayedWindows.remove(window)
        self.imageItem[window].setImage(np.zeros((2,2,3),dtype=np.uint8).transpose((1,0,2)),autoLevels=False)
        self.imageViewBox[window].setMouseEnabled(x=False,y=False)
        if window==self.selectedWindow:
            self.sliceButton.setChecked(True)
            self.zButton.setChecked(True)
            self.normDisplayCheckbox.setChecked(False)
            self.stitchCheckbox.setChecked(False)
            self.displayImageInfo()
            self.setViewBoxRange(self.displayedWindows) 
            self.clearAtlasRegions(updateImage=False)
        
    def displayImageInfo(self):
        self.updateChannelList()
        self.displayImageRange()
        self.displayPixelSize()
        self.displayImageLevels()
        
    def displayImageRange(self):
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            imageShape = self.stitchShape[self.selectedWindow] if self.stitchState[self.selectedWindow] else self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].data.shape
            self.imageDimensionsLabel.setText('XYZ Dimensions: '+str(imageShape[1])+', '+str(imageShape[0])+', '+str(imageShape[2]))
            for editBox,imgInd in zip(self.imageNumEditBoxes,self.imageIndex[self.selectedWindow]):
                editBox.setText(str(imgInd+1))
            for editBox,rng in zip(self.rangeEditBoxes,self.imageRange[self.selectedWindow]):
                editBox[0].setText(str(rng[0]+1))
                editBox[1].setText(str(rng[1]+1))
        else:
            self.imagePixelSizeLabel.setText('XYZ Dimensions: ')
            for editBox in self.imageNumEditBoxes+tuple(box for boxes in self.rangeEditBoxes for box in boxes):
                editBox.setText('')
        
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
                chInd = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannelIndex[self.selectedWindow]
                chInd = [ch for ch in chInd if ch<self.imageObjs[i].data.shape[3]]
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
            ymax,xmax = [imageShape[i]-1 for i in self.imageShapeIndex[window][:2]]
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
        self.ignoreImageRangeChange = True
        for window in windows:
            x,y,size = left,top,width
            if len(self.displayedWindows)>1:
                size /= 2
                position = self.displayedWindows.index(window)
                if len(self.displayedWindows)<3:
                    x += size/2   
                elif position in (2,3):
                    x += size
                if position in (1,3):
                    y += size
            offset = 0.01*size
            x += offset
            y += offset
            size -= 2*offset
            yRange,xRange,zRange = [self.imageRange[window][axis] for axis in self.imageShapeIndex[window]]
            yExtent,xExtent,zExtent = [r[1]-r[0] for r in (yRange,xRange,zRange)]
            if self.view3dCheckbox.isChecked():
                maxXYExtent = max(yExtent,xExtent)
                if maxXYExtent<zExtent:
                    offset = (size-size*maxXYExtent/zExtent)/2
                    x += offset
                    y += offset
                    size *= maxXYExtent/zExtent
            aspect = xExtent/yExtent
            if (len(self.displayedWindows)!=2 and aspect>1) or (len(self.displayedWindows)==2 and aspect<1):
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
                raise Warning('Must select all images displayed in the same window or in linked windows for rotation')      
        for fileInd in self.selectedFileIndex:
            self.imageObjs[fileInd].rotate90()
        affectedWindows = self.getAffectedWindows()
        if self.stitchCheckbox.isChecked():
            for window in affectedWindows:
                self.holdStitchRange = False
            self.updateStitchShape(affectedWindows)
        else:
            self.setImageRange()
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
        if self.stitchState[window]:
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
            _,contours,_ = cv2.findContours(self.getAtlasRegion(window,self.atlasRegionIDs[regionInd]).copy(order='C').astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(self.image,contours,-1,(255,255,255))
                    
    def getChannelData(self,imageObj,fileInd,window,ch):
        isSlice = not self.sliceProjState[window]
        if isSlice:
            sliceAxis = self.imageShapeIndex[window][2]
            i = self.imageIndex[window][sliceAxis]
            if self.stitchState[window]:
                i -= self.stitchPos[window,fileInd,sliceAxis]
                if not 0<=i<imageObj.data.shape[sliceAxis]:
                    return
        else:
            rng = self.imageRange[window]
        if self.xyzState[window]==2:
            if isSlice:
                channelData = imageObj.data[:,:,i,ch]
            else:
                if self.stitchCheckbox.isChecked():
                    channelData = imageObj.data[:,:,:,ch].max(axis=2)
                else:
                    channelData = imageObj.data[:,:,rng[2][0]:rng[2][1]+1,ch].max(axis=2)
        elif self.xyzState[window]==1:
            if isSlice:
                channelData = imageObj.data[i,:,:,ch].T
            else:
                if self.stitchState[window]:
                    channelData = imageObj.data[:,:,:,ch].max(axis=0).T
                else:
                    channelData = imageObj.data[rng[0][0]:rng[0][1]+1,:,:,ch].max(axis=0).T
        else:
            if isSlice:
                channelData = imageObj.data[:,i,:,ch]
            else:
                if self.stitchState[window]:
                    channelData = imageObj.data[:,:,:,ch].max(axis=1)
                else:
                    channelData = imageObj.data[:,rng[1][0]:rng[1][1]+1,:,ch].max(axis=1)
        channelData = channelData.astype(float)
        if imageObj.levels[ch][0]>0 or imageObj.levels[ch][1]<255:
            channelData -= imageObj.levels[ch][0] 
            channelData[channelData<0] = 0
            channelData *= 255/(imageObj.levels[ch][1]-imageObj.levels[ch][0])
            channelData[channelData>255] = 255
        return channelData
        
    def getAtlasRegion(self,window,region):
        isSlice = not self.sliceProjState[window]
        i = self.imageIndex[window][self.imageShapeIndex[window][2]]
        rng = self.imageRange[window]
        if self.xyzState[window]==2:
            if isSlice:
                a = self.atlasAnnotationData[:,:,i]
                a = np.in1d(a,region).reshape(a.shape)
            else:
                a = self.atlasAnnotationData[:,:,rng[2][0]:rng[2][1]+1]
                a = np.in1d(a,region).reshape(a.shape).max(axis=2)
        elif self.xyzState[window]==1:
            if isSlice:
                a = self.atlasAnnotationData[i,:,:].T
                a = np.in1d(a,region).reshape(a.shape)
            else:
                a = self.atlasAnnotationData[rng[0][0]:rng[0][1]+1,:,:]
                a = np.in1d(a,region).reshape(a.shape).max(axis=0).T
        else:
            if isSlice:
                a = self.atlasAnnotationData[:,i,:]
                a = np.in1d(a,region).reshape(a.shape)
            else:
                a = self.atlasAnnotationData[:,rng[1][0]:rng[1][1]+1,:]
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
                windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindows]
                for window in windows:
                    self.selectedAtlasRegions[window].append(ind)
        self.displayImage(windows)
        
    def clearAtlasRegions(self,updateImage=True):
        if len(self.selectedAtlasRegions[self.selectedWindow])>0:
            for region in self.atlasRegionMenu:
                if region.isChecked():
                    region.setChecked(False)
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindows]
            for window in windows:
                self.selectedAtlasRegions[window] = []
            if updateImage:
                self.displayImage(windows)
        
    def mainWinKeyPressCallback(self,event):
        key = event.key()
        modifiers = QtGui.QApplication.keyboardModifiers()
        if key in (44,46) and self.sliceButton.isChecked() and not self.view3dCheckbox.isChecked():
            axis = self.imageShapeIndex[self.selectedWindow][2]
            imgInd = self.imageIndex[self.selectedWindow][axis]
            if key==44: # <
                self.setImageNum(axis,imgInd-1)
            else: # >
                self.setImageNum(axis,imgInd+1)
        elif self.stitchCheckbox.isChecked():
            if int(modifiers & QtCore.Qt.ShiftModifier)>0:
                move = 100
            elif int(modifiers & QtCore.Qt.ControlModifier)>0:
                move = 10
            else:
                move = 1
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindows]
            fileInd = list(set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex))
            if key==16777235: # up
                self.stitchPos[windows,fileInd,0] -= move
            elif key==16777237: # down
                self.stitchPos[windows,fileInd,0] += move
            elif key==16777234: # left
                self.stitchPos[windows,fileInd,1] -= move
            elif key==16777236: # right
                self.stitchPos[windows,fileInd,1] += move
            elif key==61: # plus
                self.stitchPos[windows,fileInd,2] -= move
            elif key==45: # minus
                self.stitchPos[windows,fileInd,2] += move
            else:
                return
            self.updateStitchShape(windows)
            self.displayImage(windows)
            
    def window1MouseClickCallback(self,event):
        self.imageMouseClickCallback(event,window=0)
    
    def window2MouseClickCallback(self,event):
        self.imageMouseClickCallback(event,window=1)
        
    def window3MouseClickCallback(self,event):
        self.imageMouseClickCallback(event,window=2)
        
    def window4MouseClickCallback(self,event):
        self.imageMouseClickCallback(event,window=3)
            
    def imageMouseClickCallback(self,event,window):
        if event.button()==QtCore.Qt.LeftButton and self.view3dCheckbox.isChecked():
            x,y = int(event.pos().x()),int(event.pos().y())
            for line,pos in zip(self.view3dSliceLines[window],(y,x)):
                line.setValue(pos)
            self.updateView3dLines(axes=self.imageShapeIndex[window][:2],position=(y,x))
        
    def fileListboxSelectionCallback(self):
        self.selectedFileIndex = getSelectedItemsIndex(self.fileListbox)
        self.displayImageLevels()
        
    def fileListboxItemClickedCallback(self,item):
        fileInd = self.fileListbox.indexFromItem(item).row()
        checked = self.checkedFileIndex[self.selectedWindow]
        windows = self.displayedWindows if self.viewChannelsCheckbox.isChecked() or self.view3dCheckbox.isChecked() else [self.selectedWindow]
        if item.checkState()==QtCore.Qt.Checked and fileInd not in checked:
            if not self.stitchCheckbox.isChecked() and (len(checked)>0 or self.linkWindowsCheckbox.isChecked()) and self.imageObjs[fileInd].data.shape[:3]!=self.imageObjs[checked[0]].data.shape[:3]:
                item.setCheckState(QtCore.Qt.Unchecked)
                raise Warning('Images displayed in the same window or linked windows must be the same shape unless stitching')
            checked.append(fileInd)
            checked.sort()
            if len(checked)>1:
                if self.imageObjs[fileInd].data.shape[3]>self.channelListbox.count():
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
        else:
            if fileInd in checked:
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
        if self.stitchCheckbox.isChecked():
            self.stitchPos = np.delete(self.stitchPos,self.selectedFileIndex,axis=1)
            self.updateStitchShape(windows)
        self.selectedFileIndex = []
        if len(self.checkedFileIndex[self.selectedWindow])<1:
            if self.viewChannelsCheckbox.isChecked():
                self.setViewChannelsOff()
            elif self.view3dCheckbox.isChecked():
                self.setView3dOff()
            self.resetImageWindow()
        else:
            self.updateChannelList()
            self.displayImageLevels()
            self.displayImage(windows)
            
    def stitchCheckboxCallback(self):
        if self.stitchCheckbox.isChecked():
            if self.linkWindowsCheckbox.isChecked():
                if not (self.viewChannelsCheckbox.isChecked or self.view3dCheckbox.isChecked()):
                    self.stitchCheckbox.setChecked(False)
                    raise Warning('Stitching can not be initiated while link windows mode is on unless channel view or view 3D is selected')
                windows = self.displayedWindows
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
                windows = [self.selectedWindow]
            self.stitchPos[self.selectedWindow] = np.nan
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
            for window in windows:
                self.stitchState[window] = True
                self.holdStitchRange[window] = False
                if window!=self.selectedWindow:
                    self.stitchPos[window] = self.stitchPos[self.selectedWindow]
            self.updateStitchShape(windows)
            self.displayImageLevels()
            self.displayImage(windows)
        else:
            self.stitchState[self.selectedWindow] = False
            if len(self.checkedFileIndex[self.selectedWindow])>1:
                for i in self.checkedFileIndex[self.selectedWindow][1:]:
                    self.fileListbox.item(i).setCheckState(QtCore.Qt.Unchecked)
            if self.viewChannelsCheckbox.isChecked() or self.view3dCheckbox.isChecked():
                self.displayImageInfo()
                if self.viewChannelsCheckbox.isChecked():
                    self.setViewChannelsOn()
                else:
                    self.setView3dOn()
            else:
                self.initImageWindow()
    
    def updateStitchShape(self,windows=None):
        if windows is None:
            windows = [self.selectedWindow]
        for window in windows:
            self.stitchPos[window] -= np.nanmin(self.stitchPos[window],axis=0)
            imageShapes = np.array([self.imageObjs[i].data.shape[0:3] for i in self.checkedFileIndex[window]])
            self.stitchShape[window] = (self.stitchPos[self.selectedWindow,self.checkedFileIndex[window],:]+imageShapes).max(axis=0)
            if self.holdStitchRange[window]:
                for axis in (0,1,2):
                    if self.imageRange[window][axis][1]>=self.stitchShape[window][axis]-1:
                        self.setImageRange(axes=[axis],rangeInd=1,window=window)
            else:
                self.setImageRange(window=window)
        self.setViewBoxRangeLimits(windows)
        self.setViewBoxRange(windows)
        self.displayImageRange()
            
    def windowListboxCallback(self):
        self.selectedWindow = self.windowListbox.currentRow()
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
                raise Warning('Linking windows is not allowed while stitch mode is on unless channel view or 3D view is selected')
            if len(self.displayedWindows)>1:
                imageObj = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]]
                otherWindows = [w for w in self.displayedWindows if w!=self.selectedWindow]
                if any(self.imageObjs[self.checkedFileIndex[window][0]].data.shape[:3]!=imageObj.data.shape[:3] for window in otherWindows):
                    self.linkWindowsCheckbox.setChecked(False)
                    raise Warning('Image shapes must be equal when linking windows')
                for window in otherWindows:
                    self.imageRange[window] = self.imageRange[self.selectedWindow][:]
                self.setViewBoxRange(self.displayedWindows)
                
    def getAffectedWindows(self,chInd=None):
        return [window for window in self.displayedWindows if any(i in self.selectedFileIndex for i in self.checkedFileIndex[window]) and (chInd is None or any(ch in chInd for ch in self.selectedChannelIndex[window]))]
        
    def channelListboxCallback(self):
        if self.viewChannelsCheckbox.isChecked():
            self.viewChannelsSelectedCh = self.channelListbox.currentRow()
            self.displayImageLevels()
        else:
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
            chInd = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannelIndex[self.selectedWindow]
            for fileInd in self.selectedFileIndex:
                for ch in chInd:
                    if ch<self.imageObjs[fileInd].data.shape[3]:
                        self.imageObjs[fileInd].rgbInd[ch] = rgbInd
            self.displayImage(self.getAffectedWindows(chInd))
        
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
        self.viewChannelsSelectedCh = self.selectedChannelIndex[self.selectedWindow][0]
        self.channelListbox.setCurrentRow(self.viewChannelsSelectedCh)
        self.channelListbox.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.channelListbox.blockSignals(False)
        numCh = min(4,max(self.imageObjs[i].data.shape[3] for i in self.checkedFileIndex[self.selectedWindow]))
        self.selectedChannelIndex[:numCh] = [[ch] for ch in range(numCh)]
        for window in range(numCh):
            self.xyzState[window] = self.xyzState[self.selectedWindow]
            self.imageShapeIndex[window] = self.imageShapeIndex[self.selectedWindow]
            self.imageIndex[window] = self.imageIndex[self.selectedWindow]
        self.setLinkedViewOn(numWindows=numCh)
        
    def setViewChannelsOff(self):
        self.viewChannelsCheckbox.setChecked(False)
        self.channelListbox.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
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
        self.selectedChannelIndex[:3] = [self.selectedChannelIndex[self.selectedWindow] for _ in range(3)]
        self.xyzState[:3] = [2,1,0]
        self.imageShapeIndex[:3] = [(0,1,2),(2,1,0),(0,2,1)]
        self.imageIndex[:3] = [[(r[1]-r[0])//2 for r in self.imageRange[0]] for _ in range(3)]
        for i,editBox in enumerate(self.imageNumEditBoxes):
            editBox.setText(str(self.imageIndex[self.selectedWindow][i]))
        isSlice = self.sliceButton.isChecked()
        for window in self.displayedWindows:
            for line,ax in zip(self.view3dSliceLines[window],self.imageShapeIndex[window][:2]):
                line.setValue(self.imageIndex[window][ax])
                line.setBounds(self.imageRange[window][ax])
                line.setVisible(isSlice)
                self.imageViewBox[window].addItem(line)
        self.setLinkedViewOn(numWindows=3)
            
    def setView3dOff(self):
        self.view3dCheckbox.setChecked(False)
        for window in self.displayedWindows:
            for line in self.view3dSliceLines[window]:
                self.imageViewBox[window].removeItem(line)
        self.xyzGroupBox.setEnabled(True)
        self.setLinkedViewOff()
        
    def view3dSliceLineDragged(self):
        source = self.mainWin.sender()
        for window,lines in enumerate(self.view3dSliceLines):
            if source in lines:
                axis = self.imageShapeIndex[window][lines.index(source)]
                break 
        self.updateView3dLines([axis],[int(source.value())])
        
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
            self.sliceProjState[window] = self.sliceProjState[self.selectedWindow]
            self.imageRange[window] = self.imageRange[self.selectedWindow]
            self.normState[window] = self.normState[self.selectedWindow]
            self.stitchState[window] = self.stitchState[self.selectedWindow]
            self.selectedAtlasRegions[window] = self.selectedAtlasRegions[self.selectedWindow]
        if self.stitchState[self.selectedWindow]:
            self.stitchPos[:numWindows] = self.stitchPos[self.selectedWindow]
            self.stitchShape[:numWindows] = [self.stitchShape[self.selectedWindow] for _ in range(numWindows)]
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
            imgInd = int(self.imageNumEditBoxes[axis].text())-1
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
            
    def zoomPanButtonCallback(self):
        isOn = self.zoomPanButton.isChecked()
        for window in self.displayedWindows:
            self.imageViewBox[window].setMouseEnabled(x=isOn,y=isOn)
        
    def resetViewButtonCallback(self):
        imageShape = self.stitchShape[self.selectedWindow] if self.stitchState[self.selectedWindow] else self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].data.shape
        for editBox,size in zip(self.rangeEditBoxes,imageShape):
            editBox[0].setText('1')
            editBox[1].setText(str(size))
        self.setImageRange()
        
    def rangeEditCallback(self):
        source = self.mainWin.sender()
        for axis,boxes in enumerate(self.rangeEditBoxes):
            if source in boxes:
                rangeInd = boxes.index(source)
                break
        if rangeInd==0:
            newVal = int(self.rangeEditBoxes[axis][0].text())-1
            axMin = 0
            axMax = int(self.rangeEditBoxes[axis][1].text())-2
        else:
            newVal = int(self.rangeEditBoxes[axis][1].text())-1
            axMin = int(self.rangeEditBoxes[axis][0].text())
            axMax = self.stitchShape[self.selectedWindow][axis]-1 if self.stitchCheckbox.isChecked() else self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].data.shape[axis]-1
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
        newRange = [[int(i) for i in r] for r in reversed(self.imageViewBox[window].viewRange())]
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
            imageShape = self.stitchShape[window] if self.stitchState[window] else self.imageObjs[self.checkedFileIndex[window][0]].data.shape
            rngMax = imageShape[axes[2]]-1
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
                imageShape = self.stitchShape[window]
                self.holdStitchRange[window] = False if newRange is None and isinstance(rangeInd,slice) else True
            else:
                imageShape = self.imageObjs[self.checkedFileIndex[window][0]].data.shape
            if newRange is None: # reset min and/or max
                newRange = [[0,imageShape[axis]-1][rangeInd] for axis in axes]
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
        
    def saveImageRange(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.p')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        np.save(filePath,self.imageRange[self.selectedWindow])
    
    def loadImageRange(self):
        filePath = QtGui.QFileDialog.getOpenFileName(self.mainWin,'Choose File',self.fileOpenPath,'*.p')
        if filePath=='':
            return
        self.fileOpenPath = os.path.dirname(filePath)
        savedRange = np.load(filePath)
        imageShape = self.stitchShape[self.selectedWindow] if self.stitchState[self.selectedWindow] else self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]].data.shape
        for rangeBox,rng,size in zip(self.rangeEditBoxes,savedRange,imageShape):
            if rng[0]<0:
                rng[0] = 0
            if rng[1]>size-1:
                rng[1] = size-1
            rangeBox[0].setText(str(rng[0]+1))
            rangeBox[1].setText(str(rng[1]+1))
        self.setImageRange(savedRange)
        
    def lowLevelLineCallback(self):
        newVal = self.lowLevelLine.value()
        #self.highLevelLine.setBounds((newVal+1,255))
        self.setLevels(newVal,levelsInd=0)
         
    def highLevelLineCallback(self):
        newVal = self.highLevelLine.value()
        #self.lowLevelLine.setBounds((0,newVal-1))
        self.setLevels(newVal,levelsInd=1)
        
    def setLevels(self,newVal,levelsInd):
        chInd = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannelIndex[self.selectedWindow]
        for fileInd in self.selectedFileIndex:
            for ch in chInd:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].levels[ch][levelsInd] = newVal
        self.displayImage(self.getAffectedWindows(chInd))
        
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
        chInd = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannelIndex[self.selectedWindow]
        for fileInd in self.selectedFileIndex:
            for ch in chInd:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].gamma[ch] = newVal
        self.displayImage(self.getAffectedWindows(chInd))
        
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
        chInd = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannelIndex[self.selectedWindow]
        for fileInd in self.selectedFileIndex:
            for ch in chInd:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].alpha[ch] = newVal
        self.displayImage(self.getAffectedWindows(chInd))
        
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
        chInd = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannelIndex[self.selectedWindow]
        for fileInd in self.selectedFileIndex:
            for ch in chInd:
                if ch<self.imageObjs[fileInd].data.shape[3]:
                    self.imageObjs[fileInd].levels[ch] = [0,255]
                    self.imageObjs[fileInd].gamma[ch] = 1
                    self.imageObjs[fileInd].alpha[ch] = 1
        self.displayImage(self.getAffectedWindows(chInd))


class ImageObj():
    
    def __init__(self,filePath,fileType,numCh,chFileOrg):
        if isinstance(filePath,np.ndarray):
            self.data = filePath
        elif fileType=='Images (*.tif *.jpg *.png)':
            self.data = cv2.imread(filePath,cv2.IMREAD_UNCHANGED)
        elif fileType=='Image Series (*.tif *.jpg *.png)':
            if len(filePath)%numCh>0:
                raise Warning('Import aborted: number of files not the same for each channel')
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
                        raise Warning('Import aborted: image shapes not equal')
                if ch==0:
                    self.data = chData[:,:,:,None]
                elif chData.shape[:2]==self.data.shape[:2]:
                    self.data = np.concatenate((self.data,chData[:,:,:,None]),axis=-1)
                else:
                    raise Warning('Import aborted: image shapes not equal')
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