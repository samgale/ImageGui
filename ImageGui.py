# -*- coding: utf-8 -*-
"""
Image visualization and analysis GUI

Find Allen common coordinate framework data here:
http://help.brain-map.org/display/mouseconnectivity/API
http://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/average_template/
http://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/ara_nissl/
http://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2015/

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


def start(data=None,label=None,autoColor=False,mode=None):
    app = QtGui.QApplication.instance()
    if app is None:
        app = QtGui.QApplication([])
    imageGuiObj = ImageGui(app)
    if data is not None:
        app.processEvents()
        if not isinstance(data,list):
            data = [data]
            label = [label]
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
        self.fileOpenType = 'Images (*.tif *.jpg)'
        self.fileSavePath = self.fileOpenPath
        self.plotColorOptions = ('Reg','Green','Blue','Cyan','Yellow','Magenta','Black','White')
        self.plotColors = ('r','g','b','c','y','m','k','w')
        self.numWindows = 4
        self.imageObjs = []
        self.selectedFileIndex = []
        self.checkedFileIndex = [[] for _ in range(self.numWindows)]
        self.selectedWindow = 0
        self.displayedWindows = []
        self.selectedChannels = [[] for _ in range(self.numWindows)]
        self.sliceProjState = [0]*self.numWindows
        self.xyzState = [2]*self.numWindows
        self.ignoreImageRangeChange = False
        self.imageShapeIndex = [(0,1,2) for _ in range(self.numWindows)]
        self.imageShape = [None]*self.numWindows
        self.imageRange = [None]*self.numWindows
        self.imageIndex = [None]*self.numWindows
        self.normState = [False]*self.numWindows
        self.showBinaryState = [False]*self.numWindows
        self.stitchState = [False]*self.numWindows
        self.stitchPos = np.full((self.numWindows,1,3),np.nan)
        self.holdStitchRange = [False]*self.numWindows
        self.selectedAtlasRegions = [[] for _ in range(self.numWindows)]
        self.markedPoints = [None]*self.numWindows
        self.markPointsSize = 5
        self.markPointsColor = 'y'
        self.selectedPoint = None
        self.selectedPointWindow = None
        self.alignRefWindow = [None]*self.numWindows
        self.alignRange = [None]*self.numWindows
        self.alignAxis = [None]*self.numWindows
        self.alignIndex = [None]*self.numWindows
        
        # main window
        winHeight = 500
        winWidth = 1000
        self.mainWin = QtGui.QMainWindow()
        self.mainWin.setWindowTitle('ImageGUI')
        self.mainWin.closeEvent = self.mainWinCloseCallback
        self.mainWin.resizeEvent = self.mainWinResizeCallback
        self.mainWin.keyPressEvent = self.mainWinKeyPressCallback
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
        
        # options menu
        self.optionsMenu = self.menuBar.addMenu('Options')
        self.optionsMenuImportPointers = QtGui.QAction('Import File Pointers Instead of Data',self.mainWin,checkable=True)
        self.optionsMenuImportAutoColor = QtGui.QAction('Automatically Color Channels During Import',self.mainWin,checkable=True)
        self.optionsMenu3dLineColor = QtGui.QAction('Set View 3D Line Color',self.mainWin)
        self.optionsMenu3dLineColor.triggered.connect(self.setView3dLineColor)
        self.optionsMenu.addActions([self.optionsMenuImportPointers,self.optionsMenuImportAutoColor,self.optionsMenu3dLineColor])
        
        # image menu
        self.imageMenu = self.menuBar.addMenu('Image')
        self.imageMenuPixelSize = self.imageMenu.addMenu('Set Pixel Size')
        self.imageMenuPixelSizeXY = QtGui.QAction('XY',self.mainWin)
        self.imageMenuPixelSizeXY.triggered.connect(self.setPixelSize)
        self.imageMenuPixelSizeZ = QtGui.QAction('Z',self.mainWin)
        self.imageMenuPixelSizeZ.triggered.connect(self.setPixelSize)
        self.imageMenuPixelSize.addActions([self.imageMenuPixelSizeXY,self.imageMenuPixelSizeZ])  
        
        self.imageMenuResample = self.imageMenu.addMenu('Resample')
        self.imageMenuResamplePixelSize = QtGui.QAction('Using New Pixel Size',self.mainWin)
        self.imageMenuResamplePixelSize.triggered.connect(self.resampleImage)
        self.imageMenuResampleScaleFactor = QtGui.QAction('Using Scale Factor',self.mainWin)
        self.imageMenuResampleScaleFactor.triggered.connect(self.resampleImage)
        self.imageMenuResample.addActions([self.imageMenuResamplePixelSize,self.imageMenuResampleScaleFactor])
        
        self.imageMenuFlip = self.imageMenu.addMenu('Flip')
        self.imageMenuFlipX = QtGui.QAction('X',self.mainWin)
        self.imageMenuFlipX.triggered.connect(self.flipImage)
        self.imageMenuFlipY = QtGui.QAction('Y',self.mainWin)
        self.imageMenuFlipY.triggered.connect(self.flipImage)
        self.imageMenuFlipZ = QtGui.QAction('Z',self.mainWin)
        self.imageMenuFlipZ.triggered.connect(self.flipImage)
        self.flipOptions = (self.imageMenuFlipX,self.imageMenuFlipY,self.imageMenuFlipZ)
        self.imageMenuFlip.addActions(self.flipOptions)
        
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
        self.stitchCheckbox.clicked.connect(self.stitchCheckboxCallback)
        
        self.fileSelectLayout = QtGui.QGridLayout()
        self.fileSelectLayout.addWidget(self.moveFileDownButton,0,0,1,1)
        self.fileSelectLayout.addWidget(self.moveFileUpButton,0,1,1,1)
        self.fileSelectLayout.addWidget(self.removeFileButton,0,2,1,2)
        self.fileSelectLayout.addWidget(self.stitchCheckbox,0,8,1,2)
        self.fileSelectLayout.addWidget(self.fileListbox,1,0,9,10)
        
        # window and channel selection
        self.windowListbox = QtGui.QListWidget()
        self.windowListbox.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.windowListbox.addItems(['Window '+str(n+1) for n in range(self.numWindows)])
        self.windowListbox.setCurrentRow(0)
        self.windowListbox.itemSelectionChanged.connect(self.windowListboxCallback)
        
        self.linkWindowsCheckbox = QtGui.QCheckBox('Link Windows')
        self.linkWindowsCheckbox.clicked.connect(self.linkWindowsCheckboxCallback)
        
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
        self.viewChannelsCheckbox.clicked.connect(self.viewChannelsCheckboxCallback)
        
        self.view3dCheckbox = QtGui.QCheckBox('3D View')
        self.view3dCheckbox.clicked.connect(self.view3dCheckboxCallback)
        
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
        self.normDisplayCheckbox.clicked.connect(self.normDisplayCheckboxCallback)
        
        self.showBinaryCheckbox = QtGui.QCheckBox('Show Binary Image')
        self.showBinaryCheckbox.clicked.connect(self.showBinaryCheckboxCallback)
        
        self.gammaLabel = QtGui.QLabel('Gamma')
        self.gammaEdit = QtGui.QLineEdit('')
        self.gammaEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.gammaEdit.editingFinished.connect(self.gammaEditCallback)
        
        self.gammaSlider = QtGui.QSlider()
        self.gammaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.gammaSlider.setRange(5,300)
        self.gammaSlider.setValue(100)
        self.gammaSlider.setSingleStep(1)
        self.gammaSlider.sliderReleased.connect(self.gammaSliderCallback)
        
        self.alphaLabel = QtGui.QLabel('Alpha')
        self.alphaEdit = QtGui.QLineEdit('')
        self.alphaEdit.setAlignment(QtCore.Qt.AlignHCenter)
        self.alphaEdit.editingFinished.connect(self.alphaEditCallback)
        
        self.alphaSlider = QtGui.QSlider()
        self.alphaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.alphaSlider.setRange(0,100)
        self.alphaSlider.setValue(100)
        self.alphaSlider.setSingleStep(1)
        self.alphaSlider.sliderReleased.connect(self.alphaSliderCallback)
        
        self.levelsControlLayout = QtGui.QGridLayout()
        self.levelsControlLayout.addWidget(self.resetLevelsButton,0,0,1,2)
        self.levelsControlLayout.addWidget(self.normDisplayCheckbox,0,2,1,2)
        self.levelsControlLayout.addWidget(self.showBinaryCheckbox,1,2,1,2)
        self.levelsControlLayout.addWidget(self.gammaLabel,2,0,1,1)
        self.levelsControlLayout.addWidget(self.gammaEdit,2,1,1,1)
        self.levelsControlLayout.addWidget(self.gammaSlider,2,2,1,2)
        self.levelsControlLayout.addWidget(self.alphaLabel,3,0,1,1)
        self.levelsControlLayout.addWidget(self.alphaEdit,3,1,1,1)
        self.levelsControlLayout.addWidget(self.alphaSlider,3,2,1,2)
        
        # mark points tab        
        self.clearPointsButton = QtGui.QPushButton('Clear')
        self.clearPointsButton.clicked.connect(self.clearPointsButtonCallback)
        
        self.savePointsButton = QtGui.QPushButton('Save')
        self.savePointsButton.clicked.connect(self.savePointsButtonCallback)
        
        self.decreasePointSizeButton = QtGui.QPushButton('-')
        self.decreasePointSizeButton.clicked.connect(self.decreasePointSizeButtonCallback)
        
        self.increasePointSizeButton = QtGui.QPushButton('+')
        self.increasePointSizeButton.clicked.connect(self.increasePointSizeButtonCallback)
        
        self.markPointsColorMenu = QtGui.QComboBox()
        self.markPointsColorMenu.addItems(self.plotColorOptions)
        self.markPointsColorMenu.setCurrentIndex(4)
        self.markPointsColorMenu.currentIndexChanged.connect(self.markPointsColorMenuCallback)
        
        self.markPointsTable = QtGui.QTableWidget(1,3)
        self.markPointsTable.resizeEvent = self.markPointsTableResizeCallback
        self.markPointsTable.keyPressEvent = self.markPointsTableKeyPressCallback
        self.markPointsTable.setHorizontalHeaderLabels(['X','Y','Z'])
        for col in range(3):
            item = QtGui.QTableWidgetItem('')
            item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.markPointsTable.setItem(0,col,item)
        
        self.markPointsLayout = QtGui.QGridLayout()
        self.markPointsLayout.addWidget(self.clearPointsButton,0,0,1,2)
        self.markPointsLayout.addWidget(self.savePointsButton,1,0,1,2)
        self.markPointsLayout.addWidget(self.markPointsColorMenu,0,2,1,2)
        self.markPointsLayout.addWidget(self.decreasePointSizeButton,1,2,1,1)
        self.markPointsLayout.addWidget(self.increasePointSizeButton,1,3,1,1)
        self.markPointsLayout.addWidget(self.markPointsTable,2,0,4,4)
        self.markPointsTab = QtGui.QWidget()
        self.markPointsTab.setLayout(self.markPointsLayout)
        self.utilityTabs = QtGui.QTabWidget()
        self.utilityTabs.addTab(self.markPointsTab,'Mark Points')
        
        # align tab
        self.alignRefLabel = QtGui.QLabel('Reference')
        self.alignRefMenu = QtGui.QComboBox()
        self.alignRefMenu.addItems(['Window '+str(n+1) for n in range(self.numWindows)])
        self.alignRefMenu.setCurrentIndex(0)
        
        self.alignStartLabel = QtGui.QLabel('Start')
        self.alignStartEdit = QtGui.QLineEdit('')
        self.alignStartEdit.setAlignment(QtCore.Qt.AlignHCenter)
        
        self.alignEndLabel = QtGui.QLabel('End')
        self.alignEndEdit = QtGui.QLineEdit('')
        self.alignEndEdit.setAlignment(QtCore.Qt.AlignHCenter)
        
        self.alignCheckbox = QtGui.QCheckBox('Align')
        self.alignCheckbox.clicked.connect(self.alignCheckboxCallback)
        
        self.alignLayout = QtGui.QGridLayout()
        self.alignLayout.addWidget(self.alignRefLabel,0,0,1,1)
        self.alignLayout.addWidget(self.alignRefMenu,0,1,1,1)
        self.alignLayout.addWidget(self.alignStartLabel,1,0,1,1)
        self.alignLayout.addWidget(self.alignStartEdit,1,1,1,1)
        self.alignLayout.addWidget(self.alignEndLabel,2,0,1,1)
        self.alignLayout.addWidget(self.alignEndEdit,2,1,1,1)
        self.alignLayout.addWidget(self.alignCheckbox,3,0,1,2)
        self.alignTab = QtGui.QWidget()
        self.alignTab.setLayout(self.alignLayout)
        self.utilityTabs.addTab(self.alignTab,'Align')
        
        # warp tab
        self.warpRefLabel = QtGui.QLabel('Reference')
        self.warpRefMenu = QtGui.QComboBox()
        self.warpRefMenu.addItems(['Window '+str(n+1) for n in range(self.numWindows)])
        self.warpRefMenu.setCurrentIndex(0)
        
        self.warpAllCheckbox = QtGui.QCheckBox('Apply All')
        
        self.copyPointsCheckbox = QtGui.QCheckBox('Copy Points')
        self.copyPointsCheckbox.clicked.connect(self.copyPointsCheckboxCallback)
        
        self.transformButton = QtGui.QPushButton('Transform')
        self.transformButton.clicked.connect(self.transformButtonCallback)
        
        self.warpButton = QtGui.QPushButton('Warp')
        self.warpButton.clicked.connect(self.warpButtonCallback)
        
        self.warpLayout = QtGui.QGridLayout()
        self.warpLayout.addWidget(self.warpRefLabel,0,0,1,1)
        self.warpLayout.addWidget(self.warpRefMenu,0,1,1,1)
        self.warpLayout.addWidget(self.warpAllCheckbox,1,0,1,1)
        self.warpLayout.addWidget(self.copyPointsCheckbox,1,1,1,1)
        self.warpLayout.addWidget(self.transformButton,2,0,1,1)
        self.warpLayout.addWidget(self.warpButton,2,1,1,1)
        self.warpTab = QtGui.QWidget()
        self.warpTab.setLayout(self.warpLayout)
        self.utilityTabs.addTab(self.warpTab,'Warp')
        
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
        
    def mainWinCloseCallback(self,event):
        event.accept()
        
    def mainWinResizeCallback(self,event):
        if len(self.displayedWindows)>0:
            self.setViewBoxRange(self.displayedWindows)
        
    def saveImage(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.tif')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        yRange,xRange = [self.imageRange[self.selectedWindow][axis] for axis in self.imageShapeIndex[self.selectedWindow][:2]]
        cv2.imwrite(filePath,self.getImage()[yRange[0]:yRange[1]+1,xRange[0]:xRange[1]+1,::-1])
        
    def saveVolume(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.tif')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        imageIndex = self.imageIndex[self.selectedWindow]
        yRange,xRange,zRange = [self.imageRange[self.selectedWindow][axis] for axis in self.imageShapeIndex[self.selectedWindow]]
        for i in range(zRange[0],zRange[1]+1):
            self.imageIndex[self.selectedWindow] = i
            cv2.imwrite(filePath[:-4]+'_'+str(i)+'.tif',self.getImage()[yRange[0]:yRange[1]+1,xRange[0]:xRange[1]+1,::-1])
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
                chFileOrg,ok = QtGui.QInputDialog.getItem(self.mainWin,'Import Image Series','Channel file organization:',('alternating','blocks','rgb'))
                if not ok:
                    return
            if chFileOrg=='rgb':
                if numCh!=3:
                    raise Warning('Number of channels must equal 3 for rgb channel file organization')
            elif len(filePaths[0])%numCh>0:
                raise Warning('Number of files must be the same for each channel')
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
        loadData = not self.optionsMenuImportPointers.isChecked()
        autoColor = self.optionsMenuImportAutoColor.isChecked()
        for filePath in filePaths:
            self.loadImageData(filePath,fileType,numCh,chFileOrg,loadData,autoColor)
        
    def loadImageData(self,filePath,fileType,numCh=None,chFileOrg=None,loadData=True,autoColor=False):
        # filePath and fileType can also be a numpy array (Y x X x Z x Channels) and optional label, respectively
        # Provide numCh and chFileOrg if importing a multiple file image series
        self.imageObjs.append(ImageObj(filePath,fileType,numCh,chFileOrg,loadData,autoColor))
        if isinstance(filePath,np.ndarray):
            label = 'data_'+time.strftime('%Y%m%d_%H%M%S') if fileType is None else fileType
        else:
            label = filePath[0] if isinstance(filePath,list) else filePath
        self.fileListbox.addItem(label)
        if len(self.imageObjs)>1:
            self.fileListbox.item(self.fileListbox.count()-1).setCheckState(QtCore.Qt.Unchecked)
            if self.stitchCheckbox.isChecked():
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
        self.imageItem[window].setImage(np.zeros((2,2,3),dtype=np.uint8).transpose((1,0,2)),autoLevels=False)
        self.imageViewBox[window].setMouseEnabled(x=False,y=False)
        self.imageViewBox[window].setZValue(0)
        self.clearMarkedPoints([window])
        self.alignRefWindow[window] = None
        if window==self.selectedWindow:
            self.sliceButton.setChecked(True)
            self.zButton.setChecked(True)
            self.normDisplayCheckbox.setChecked(False)
            self.stitchCheckbox.setChecked(False)
            self.displayImageInfo()
            self.setViewBoxRange(self.displayedWindows) 
            self.clearAtlasRegions(updateImage=False)
            self.alignCheckbox.setChecked(False)
        
    def displayImageInfo(self):
        self.updateChannelList()
        self.displayImageRange()
        self.displayPixelSize()
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
        if self.mainWin.sender() is self.imageMenuPixelSizeXY:
            dim = 'XY'
            ind = (0,1)
        else:
            dim = 'Z'
            ind = (2,)
        val,ok = QtGui.QInputDialog.getDouble(self.mainWin,'Set '+dim+' Pixel Size','\u03BCm/pixel:',0,min=0,decimals=4)
        if ok and val>0:
            for fileInd in self.selectedFileIndex:
                for i in ind:
                    self.imageObjs[fileInd].pixelSize[i] = val
            self.displayPixelSize()
            
    def resampleImage(self):
        sender = self.mainWin.sender()
        if sender==self.imageMenuResamplePixelSize:
            if any(self.imageObjs[fileInd].pixelSize[0] is None for fileInd in self.selectedFileIndex):
                raise Warning('Must define pixel size before using new pixel size for resampling')
            newPixelSize,ok = QtGui.QInputDialog.getDouble(self.mainWin,'Resample Pixel Size','\u03BCm/pixel:',0,min=0,decimals=4)
            if not ok or newPixelSize==0:
                return
        else:
            scaleFactor,ok = QtGui.QInputDialog.getDouble(self.mainWin,'Resample Scale Factor','scale factor (new/old size):',1,min=0.001,decimals=4)
            if not ok or scaleFactor==1:
                return
        self.checkIfSelectedDisplayedBeforeShapeChange()            
        for fileInd in self.selectedFileIndex:
            oldPixelSize = self.imageObjs[fileInd].pixelSize[0]
            if sender==self.imageMenuResamplePixelSize:
                scaleFactor = oldPixelSize/newPixelSize
            else:
                newPixelSize = None if oldPixelSize is None else round(oldPixelSize/scaleFactor,4)
            if newPixelSize is not None:
                self.imageObjs[fileInd].pixelSize[:2] = [newPixelSize]*2
            shape = self.imageObjs[fileInd].shape
            shape = tuple(int(round(shape[i]*scaleFactor)) for i in (0,1))+shape[2:]
            scaledData = np.zeros(shape,dtype=np.uint8)
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
        option = self.flipOptions.index(self.mainWin.sender())
        for fileInd in self.selectedFileIndex:
            if option==0:
                self.imageObjs[fileInd].flipX()
            elif option==1:
                self.imageObjs[fileInd].flipY()
            else:
                self.imageObjs[fileInd].flipZ()
        self.displayImage(self.getAffectedWindows())
        
    def rotateImage90(self):
        self.checkIfSelectedDisplayedBeforeShapeChange()
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
        
    def checkIfSelectedDisplayedBeforeShapeChange(self):
        for window in self.displayedWindows:
            selected = [True if i in self.selectedFileIndex else False for i in self.checkedFileIndex[window]]
            if (self.linkWindowsCheckbox.isChecked() or any(selected)) and not all(selected):
                raise Warning('Must select all images displayed in the same window or in linked windows before shape change')      
    
    def displayImageLevels(self):
        fileInd = list(set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex))
        if len(fileInd)>0:
            isSet = False
            pixIntensityHist = np.zeros(256)
            for i in fileInd:
                channels = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannels[self.selectedWindow]
                channels = [ch for ch in channels if ch<self.imageObjs[i].shape[3]]
                if len(channels)>0:
                    hist,_ = np.histogram(self.imageObjs[i].getData(channels),bins=256,range=(0,256))
                    pixIntensityHist += hist
                    if not isSet:
                        self.lowLevelLine.setValue(self.imageObjs[i].levels[channels[0]][0])
                        self.highLevelLine.setValue(self.imageObjs[i].levels[channels[0]][1])
                        self.gammaEdit.setText(str(self.imageObjs[i].gamma[channels[0]]))
                        self.gammaSlider.setValue(self.imageObjs[i].gamma[channels[0]]*100)
                        self.alphaEdit.setText(str(self.imageObjs[i].alpha))
                        self.alphaSlider.setValue(self.imageObjs[i].alpha*100)
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
            ymax,xmax = [self.imageShape[window][i]-1 for i in self.imageShapeIndex[window][:2]]
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
        
    def displayImage(self,windows=None):
        if windows is None:
            windows = [self.selectedWindow]
        for window in windows:
            self.imageItem[window].setImage(self.getImage(window).transpose((1,0,2)),autoLevels=False)
        self.plotMarkedPoints(windows)
        
    def getImage(self,window=None):
        if window is None:
            window = self.selectedWindow
        imageShape = [self.imageShape[window][i] for i in self.imageShapeIndex[window][:2]]
        image = np.zeros((imageShape[0],imageShape[1],3))
        for fileInd in self.checkedFileIndex[window]:
            imageObj = self.imageObjs[fileInd]
            if self.stitchState[window]:
                i,j = (slice(self.stitchPos[window,fileInd,i],self.stitchPos[window,fileInd,i]+imageObj.shape[i]) for i in self.imageShapeIndex[window][:2])
            else:
                i,j = (slice(0,imageObj.shape[i]) for i in self.imageShapeIndex[window][:2])
            channels = [ch for ch in self.selectedChannels[window] if ch<imageObj.shape[3]]
            data,alphaMap = self.getImageData(imageObj,fileInd,window,channels)
            if data is not None:
                if not self.stitchState[window]:
                    if alphaMap is not None:
                        image *= 1-alphaMap
                    if imageObj.alpha<1:
                        image *= 1-imageObj.alpha
                for ind,ch in enumerate(channels):
                    for k in imageObj.rgbInd[ch]:
                        if self.stitchState[window]:
                            image[i,j,k] = np.maximum(image[i,j,k],data[:,:,ind])
                        elif imageObj.alpha<1 or alphaMap is not None:
                            image[i,j,k] += data[:,:,ind]
                        else:
                            image[i,j,k] = data[:,:,ind]
        if self.normState[window]:
            image -= image.min()
            image.clip(min=0,out=image)
            if image.any():
                image *= 255/image.max()
        image = image.astype(np.uint8)
        for regionInd in self.selectedAtlasRegions[window]:
            _,contours,_ = cv2.findContours(self.getAtlasRegion(window,self.atlasRegionIDs[regionInd]).copy(order='C').astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(image,contours,-1,(255,255,255))
        return image
                    
    def getImageData(self,imageObj,fileInd,window,channels):
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
                i -= self.stitchPos[window,fileInd,axis]
                if not 0<=i<imageObj.shape[axis]:
                    return None,None
            rangeSlice = slice(i,i+1)
        if axis==2:
            data = imageObj.getData(channels,rangeSlice)
        elif imageObj.data is None:
            data = np.zeros([imageObj.shape[i] for i in self.imageShapeIndex[window][:2]]+[len(channels)],dtype=np.uint8)
            dataIter = imageObj.getDataIterator(channels)
            for i in range(imageObj.shape[2]):
                for chInd,_ in enumerate(channels):
                    if axis==1:
                        data[:,i,chInd] = next(dataIter)[:,rangeSlice]
                    else:
                        data[i,:,chInd] = next(dataIter)[rangeSlice,:]
        elif axis==1:
            data = imageObj.data[:,rangeSlice,:,channels]
        else:
            data = imageObj.data[rangeSlice,:,:,channels].transpose((0,2,1,3))
        data = data.max(axis).astype(float)
        for chInd,ch in enumerate(channels):
            chData = data[:,:,chInd]
            if self.showBinaryState[window]:
                aboveThresh = chData>=imageObj.levels[ch][1]
                chData[aboveThresh] = 255
                chData[np.logical_not(aboveThresh)] = 0
            else:
                if imageObj.levels[ch][0]>0 or imageObj.levels[ch][1]<255:
                    chData -= imageObj.levels[ch][0] 
                    chData.clip(min=0,out=chData)
                    chData *= 255/(imageObj.levels[ch][1]-imageObj.levels[ch][0])
                    chData.clip(max=255,out=chData)
                if imageObj.gamma[ch]!=1:
                    chData /= 255
                    chData **= imageObj.gamma[ch]
                    chData *= 255
        if imageObj.alphaMap is None:
            alphaMap = None
        else:
            if axis==2:
                alphaMap = imageObj.alphaMap[:,:,rangeSlice]
            elif axis==1:
                alphaMap = imageObj.alphaMap[:,rangeSlice,:]
            else:
                alphaMap = imageObj.alphaMap[rangeSlice,:,:].transpose((0,2,1))
            alphaMap = (alphaMap.max(axis).astype(float)/255)[:,:,None]
            data *= alphaMap
        if imageObj.alpha<1:
            data *= imageObj.alpha
        return data,alphaMap
        
    def getAtlasRegion(self,window,region):
        isProj = self.sliceProjState[window]
        axis = self.imageShapeIndex[window][2]
        if isProj:
            rng = self.imageRange[window][axis]
            ind = slice(rng[0],rng[1]+1)
        else:
            ind = self.imageIndex[window][axis]
        if axis==2:
            a = self.atlasAnnotationData[:,:,ind]
        elif axis==1:
            a = self.atlasAnnotationData[:,ind,:]
        else:
            a = self.atlasAnnotationData.transpose((0,2,1))[ind,:,:]
        a = np.in1d(a,region).reshape(a.shape)
        if isProj:
            a = a.max(axis=axis)
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
                windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
                for window in windows:
                    self.selectedAtlasRegions[window].append(ind)
        self.displayImage(windows)
        
    def clearAtlasRegions(self,updateImage=True):
        if len(self.selectedAtlasRegions[self.selectedWindow])>0:
            for region in self.atlasRegionMenu:
                if region.isChecked():
                    region.setChecked(False)
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            for window in windows:
                self.selectedAtlasRegions[window] = []
            if updateImage:
                self.displayImage(windows)
        
    def mainWinKeyPressCallback(self,event):
        key = event.key()
        if key in (44,46) and self.sliceButton.isChecked() and not self.view3dCheckbox.isChecked():
            axis = self.imageShapeIndex[self.selectedWindow][2]
            imgInd = self.imageIndex[self.selectedWindow][axis]
            if key==44: # <
                self.setImageNum(axis,imgInd-1)
            else: # >
                self.setImageNum(axis,imgInd+1)
        elif self.stitchCheckbox.isChecked() and key in (16777237,16777235,16777234,16777236,45,61):
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            fileInd = list(set(self.checkedFileIndex[self.selectedWindow]) & set(self.selectedFileIndex))
            moveAxis,moveDist = self.getMoveParams(self.selectedWindow,key)
            self.stitchPos[windows,fileInd,moveAxis] += moveDist
            self.updateStitchShape(windows)
            self.displayImage(windows)
        elif self.selectedPoint is not None and key in (QtCore.Qt.Key_Delete,16777237,16777235,16777234,16777236):
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedPointWindow]
            for window in windows:
                imgAxis = self.imageShapeIndex[window][2]
                if self.markedPoints[window][self.selectedPoint,imgAxis]==self.imageIndex[window][imgAxis]:
                    if key==QtCore.Qt.Key_Delete:
                        if self.markedPoints[window].shape[0]>1:
                            self.markedPoints[window] = np.delete(self.markedPoints[window],self.selectedPoint,0)
                            if window==self.selectedWindow:
                                self.markPointsTable.removeRow(self.selectedPoint)
                            self.selectedPoint = None
                            self.plotMarkedPoints([window])
                        else:
                            self.clearMarkedPoints([window])
                    else:
                        moveAxis,moveDist = self.getMoveParams(window,key,True)
                        point = self.markedPoints[window][self.selectedPoint]
                        point[moveAxis] += moveDist
                        rng = self.imageRange[window][moveAxis]
                        if point[moveAxis]<rng[0]:
                            point[moveAxis] = rng[0]
                        elif point[moveAxis]>rng[1]:
                            point[moveAxis] = rng[1]
                        if window==self.selectedWindow:
                            ind = 2 if moveAxis==2 else int(not moveAxis)
                            self.markPointsTable.item(self.selectedPoint,ind).setText(str(point[moveAxis]+1))
                        self.plotMarkedPoints([window])
                    
    def getMoveParams(self,window,key,flipVert=False):
        down,up = 16777237,16777235
        if flipVert:
            up,down = down,up
        if key in (down,up):
            axis = self.imageShapeIndex[window][0]
        elif key in (16777234,16777236): # left,right
            axis = self.imageShapeIndex[window][1]
        else: # minus,plus
            axis = self.imageShapeIndex[window][2]
        modifiers = self.app.keyboardModifiers()
        if int(modifiers & QtCore.Qt.ShiftModifier)>0:
            dist = 100
        elif int(modifiers & QtCore.Qt.ControlModifier)>0:
            dist = 10
        else:
            dist = 1
        if key in (down,16777234,45):
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
        if event.button()==QtCore.Qt.LeftButton:
            if self.view3dCheckbox.isChecked():
                for line,pos in zip(self.view3dSliceLines[window],(y,x)):
                    line.setValue(pos)
                self.updateView3dLines(axes=self.imageShapeIndex[window][:2],position=(y,x))
            elif not self.viewChannelsCheckbox.isChecked():
                self.windowListbox.setCurrentRow(window)
        elif event.button()==QtCore.Qt.RightButton and self.markedPoints[window] is not None:
            axis = self.imageShapeIndex[window][2]
            rows = np.where(self.markedPoints[window][:,axis]==self.imageIndex[window][axis])[0]
            if len(rows)>0:
                self.selectedPoint = rows[np.argmin(np.sum(np.absolute(self.markedPoints[window][rows,:][:,self.imageShapeIndex[window][:2]]-[y,x]),axis=1))]
                self.selectedPointWindow = window
        
    def imageDoubleClickCallback(self,event,window):
        x,y = event.pos().x(),event.pos().y()
        newPoint = np.array([y,x,self.imageIndex[window][self.imageShapeIndex[window][2]]])[list(self.imageShapeIndex[window])]
        windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [window]
        for window in windows:
            self.markedPoints[window] = newPoint[None,:] if self.markedPoints[window] is None else np.concatenate((self.markedPoints[window],newPoint[None,:]))
            if window==self.selectedWindow:
                self.fillPointsTable(newPoint=True)
        self.selectedPoint = self.markedPoints[window].shape[0]-1
        self.selectedPointWindow = window
        self.plotMarkedPoints(windows)
        
    def fileListboxSelectionCallback(self):
        self.selectedFileIndex = getSelectedItemsIndex(self.fileListbox)
        self.displayImageLevels()
        
    def fileListboxItemClickedCallback(self,item):
        fileInd = self.fileListbox.indexFromItem(item).row()
        checked = self.checkedFileIndex[self.selectedWindow]
        windows = self.displayedWindows if self.viewChannelsCheckbox.isChecked() or self.view3dCheckbox.isChecked() else [self.selectedWindow]
        if item.checkState()==QtCore.Qt.Checked and fileInd not in checked:
            if not self.stitchCheckbox.isChecked() and (len(checked)>0 or self.linkWindowsCheckbox.isChecked()) and self.imageObjs[fileInd].shape[:3]!=self.imageObjs[checked[0]].shape[:3]:
                item.setCheckState(QtCore.Qt.Unchecked)
                raise Warning('Images displayed in the same window or linked windows must be the same shape unless stitching')
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
        if self.stitchCheckbox.isChecked():
            self.stitchPos = np.delete(self.stitchPos,self.selectedFileIndex,axis=1)
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
                        pos[0] += self.imageObjs[i].shape[0]
                        pos[1] = 0
                    elif col>0:
                        pos[1] += self.imageObjs[i].shape[1]
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
                del(self.checkedFileIndex[self.selectedWindow][1:])
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
            tileShapes = np.array([self.imageObjs[i].shape[:3] for i in self.checkedFileIndex[window]])
            self.imageShape[window] = (self.stitchPos[self.selectedWindow,self.checkedFileIndex[window],:]+tileShapes).max(axis=0)
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
        self.sliceProjButtons[self.sliceProjState[window]].setChecked(True)
        self.xyzButtons[self.xyzState[window]].setChecked(True)
        self.normDisplayCheckbox.setChecked(self.normState[window])
        self.showBinaryCheckbox.setChecked(self.showBinaryState[window])
        self.stitchCheckbox.setChecked(self.stitchState[window])
        for ind,region in enumerate(self.atlasRegionMenu):
            region.setChecked(ind in self.selectedAtlasRegions[window])
        self.clearPointsTable()
        self.fillPointsTable()
        isAligned = self.alignRefWindow[window] is not None
        self.alignCheckbox.setChecked(isAligned)
        alignRange = [str(self.alignRange[window][i]+1) for i in (0,1)] if isAligned else ('','')
        self.alignStartEdit.setText(alignRange[0])
        self.alignEndEdit.setText(alignRange[1])
        self.displayImageInfo()
    
    def linkWindowsCheckboxCallback(self):
        if self.linkWindowsCheckbox.isChecked():
            if self.stitchCheckbox.isChecked():
                self.linkWindowsCheckbox.setChecked(False)
                raise Warning('Linking windows is not allowed while stitch mode is on unless channel view or 3D view is selected')
            if len(self.displayedWindows)>1:
                imageObj = self.imageObjs[self.checkedFileIndex[self.selectedWindow][0]]
                otherWindows = [w for w in self.displayedWindows if w!=self.selectedWindow]
                if any(self.imageObjs[self.checkedFileIndex[window][0]].shape[:3]!=imageObj.shape[:3] for window in otherWindows):
                    self.linkWindowsCheckbox.setChecked(False)
                    raise Warning('Image shapes must be equal when linking windows')
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
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
            channels = getSelectedItemsIndex(self.channelListbox)
            for window in windows:
                self.selectedChannels[window] = channels
            self.displayImageLevels()
            self.displayImage(windows)
        
    def updateChannelList(self):
        self.channelListbox.blockSignals(True)
        self.channelListbox.clear()
        if len(self.checkedFileIndex[self.selectedWindow])>0:
            numCh = max(self.imageObjs[i].shape[3] for i in self.checkedFileIndex[self.selectedWindow])
            for ch in range(numCh):
                item = QtGui.QListWidgetItem('Ch '+str(ch+1),self.channelListbox)
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
        self.channelListbox.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
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
        
    def setView3dLineColor(self):
        color,ok = QtGui.QInputDialog.getItem(self.mainWin,'Set View 3D Line Color','Choose Color',self.plotColorOptions,editable=False)
        if ok:
            color = self.plotColors[self.plotColorOptions.index(color)]
            for windowLines in self.view3dSliceLines:
                for line in windowLines:
                    line.setPen(color)
        
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
            self.imageShape[window] = self.imageShape[self.selectedWindow]
            self.imageRange[window] = self.imageRange[self.selectedWindow]
            self.normState[window] = self.normState[self.selectedWindow]
            self.showBinaryState[window] = self.showBinaryState[self.selectedWindow]
            self.stitchState[window] = self.stitchState[self.selectedWindow]
            self.selectedAtlasRegions[window] = self.selectedAtlasRegions[self.selectedWindow]
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
            if not self.linkWindowsCheckbox.isChecked():
                self.alignWindows(self.selectedWindow,axis)
            
    def zoomPanButtonCallback(self):
        isOn = self.zoomPanButton.isChecked()
        for window in self.displayedWindows:
            self.imageViewBox[window].setMouseEnabled(x=isOn,y=isOn)
        
    def resetViewButtonCallback(self):
        isDisplayed = len(self.checkedFileIndex[self.selectedWindow])>0
        for axis,editBoxes in enumerate(self.rangeEditBoxes):
            if isDisplayed:
                editBoxes[0].setText('1')
                editBoxes[1].setText(str(self.imageShape[self.selectedWindow][axis]))
            else:
                for box in editBoxes:
                    box.setText('')
        if isDisplayed:
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
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.npy')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        np.save(filePath,self.imageRange[self.selectedWindow])
    
    def loadImageRange(self):
        filePath = QtGui.QFileDialog.getOpenFileName(self.mainWin,'Choose File',self.fileOpenPath,'*.npy')
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
        newVal = self.lowLevelLine.value()
        #self.highLevelLine.setBounds((newVal+1,255))
        self.setLevels(newVal,levelsInd=0)
         
    def highLevelLineCallback(self):
        newVal = self.highLevelLine.value()
        #self.lowLevelLine.setBounds((0,newVal-1))
        self.setLevels(newVal,levelsInd=1)
        
    def setLevels(self,newVal,levelsInd):
        channels = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannels[self.selectedWindow]
        for fileInd in self.selectedFileIndex:
            for ch in channels:
                if ch<self.imageObjs[fileInd].shape[3]:
                    self.imageObjs[fileInd].levels[ch][levelsInd] = newVal
        self.displayImage(self.getAffectedWindows(channels))
        
    def resetLevelsButtonCallback(self):
        self.lowLevelLine.setValue(0)
        self.highLevelLine.setValue(255)
        self.gammaEdit.setText('1')
        self.gammaSlider.setValue(100)
        self.alphaEdit.setText('1')
        self.alphaSlider.setValue(100)
        channels = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannels[self.selectedWindow]
        for fileInd in self.selectedFileIndex:
            for ch in channels:
                if ch<self.imageObjs[fileInd].shape[3]:
                    self.imageObjs[fileInd].levels[ch] = [0,255]
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
        channels = [self.viewChannelsSelectedCh] if self.viewChannelsCheckbox.isChecked() else self.selectedChannels[self.selectedWindow]
        for fileInd in self.selectedFileIndex:
            for ch in channels:
                if ch<self.imageObjs[fileInd].shape[3]:
                    self.imageObjs[fileInd].gamma[ch] = newVal
        self.displayImage(self.getAffectedWindows(channels))
        
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
            self.imageObjs[fileInd].alpha = newVal
        self.displayImage(self.getAffectedWindows())
        
    def plotMarkedPoints(self,windows=None):
        if windows is None:
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow] 
        for window in windows:
            if self.markedPoints[window] is None:
                x = y = []
            else:
                axis = self.imageShapeIndex[window][2]
                rng = self.imageRange[window][axis] if self.sliceProjState[window] else [self.imageIndex[window][axis]]*2
                rows = np.logical_and(self.markedPoints[window][:,axis]>=rng[0],self.markedPoints[window][:,axis]<=rng[1])
                if any(rows):
                    y,x = self.markedPoints[window][rows,:][:,self.imageShapeIndex[window][:2]].T
                else:
                    x = y = []
            self.markPointsPlot[window].setData(x=x,y=y,symbolSize=self.markPointsSize,symbolPen=self.markPointsColor)
        
    def fillPointsTable(self,newPoint=False):
        if self.markedPoints[self.selectedWindow] is not None:
            numPts = self.markedPoints[self.selectedWindow].shape[0]
            if newPoint:
                if numPts>1:
                    self.markPointsTable.insertRow(numPts-1)
                rows = [numPts-1]
            else:
                self.markPointsTable.setRowCount(numPts)
                rows = range(numPts)
            for row in rows:
                pt = [str(round(self.markedPoints[self.selectedWindow][row,i],2)+1) for i in (1,0,2)]
                for col in range(3):
                    if row>0:
                        item = QtGui.QTableWidgetItem(pt[col])
                        item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                        self.markPointsTable.setItem(row,col,item)
                    else:
                        self.markPointsTable.item(row,col).setText(pt[col])
                
    def clearPointsTable(self):
        self.markPointsTable.setRowCount(1)
        for col in range(3):
            self.markPointsTable.item(0,col).setText('')
    
    def clearPointsButtonCallback(self):
        self.clearMarkedPoints()
        
    def clearMarkedPoints(self,windows=None):
        if windows is None:
            windows = self.displayedWindows if self.linkWindowsCheckbox.isChecked() else [self.selectedWindow]
        for window in windows:
            self.markedPoints[window] = None
            if self.selectedPoint is not None and window==self.selectedPointWindow:
                self.selectedPoint = None
            if window==self.selectedWindow:
                self.clearPointsTable()
        self.plotMarkedPoints(windows)
    
    def decreasePointSizeButtonCallback(self):
        if self.markPointsSize>1:
            self.markPointsSize -= 1
            self.plotMarkedPoints(self.displayedWindows)
    
    def increasePointSizeButtonCallback(self):
        self.markPointsSize += 1
        self.plotMarkedPoints(self.displayedWindows)
    
    def markPointsColorMenuCallback(self):
        self.markPointsColor = self.plotColors[self.markPointsColorMenu.currentIndex()]
        self.plotMarkedPoints(self.displayedWindows) 
        
    def savePointsButtonCallback(self):
        filePath = QtGui.QFileDialog.getSaveFileName(self.mainWin,'Save As',self.fileSavePath,'*.npy')
        if filePath=='':
            return
        self.fileSavePath = os.path.dirname(filePath)
        np.save(filePath,self.markedPoints[self.selectedWindow][:,(1,0,2)]+1)
        
    def markPointsTableResizeCallback(self,event):
        w = int(self.markPointsTable.viewport().width()/3)
        for col in range(self.markPointsTable.columnCount()):
            self.markPointsTable.setColumnWidth(col,w)
        
    def markPointsTableKeyPressCallback(self,event):
        key = event.key()
        modifiers = QtGui.QApplication.keyboardModifiers()
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
        
    def alignCheckboxCallback(self):
        if self.alignCheckbox.isChecked():
            refWin = self.alignRefMenu.currentIndex()
            axis = self.imageShapeIndex[self.selectedWindow][2]
            refSize = self.imageShape[refWin][axis]
            start,end = int(self.alignStartEdit.text())-1,int(self.alignEndEdit.text())-1
            reverse = False
            if start>end:
                start,end = end,start
                reverse = True
            if start<0 or end>=refSize:
                self.alignCheckbox.setChecked(False)
                raise Warning('Align start and end must be between 0 and the reference image axis length')
            self.alignRefWindow[self.selectedWindow] = refWin
            self.alignRange[self.selectedWindow] = [end,start] if reverse else [start,end]
            self.alignAxis[self.selectedWindow] = axis
            n = end-start+1
            rng = self.imageRange[self.selectedWindow][axis]
            interval = n/(rng[1]-rng[0]+1)
            alignInd = np.arange(n)/interval+rng[0]
            self.alignIndex[self.selectedWindow] = -np.ones(refSize,dtype=int)
            self.alignIndex[self.selectedWindow][start:end+1] = alignInd[::-1] if reverse else alignInd
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
                self.imageIndex[self.alignRefWindow[window]][axis] = np.where(self.alignIndex[window]==self.imageIndex[window][axis])[0][0]
                self.displayImage([self.alignRefWindow[window]])
    
    def transformButtonCallback(self):
        imageContours = []
        for window in (self.warpRefMenu.currentIndex(),self.selectedWindow):
            binState = self.showBinaryState[window]
            self.showBinaryState[window] = True
            imageContours.append(drawContour(self.getImage(window).max(axis=2)))
            self.showBinaryState[window] = binState
        template,warpImage = imageContours
        _,warpMatrix = cv2.findTransformECC(template,warpImage,np.eye(2,3,dtype=np.float32),cv2.MOTION_AFFINE)
        for fileInd in self.checkedFileIndex[self.selectedWindow]:
            imageObj = self.imageObjs[fileInd]
            i = self.imageIndex[self.selectedWindow]
            warpData = np.zeros(template.shape+imageObj.shape[2:],dtype=np.uint8)
            for ch in range(imageObj.shape[3]):
                warpData[:,:,i,ch] = cv2.warpAffine(imageObj.getData(ch,i),warpMatrix,template.shape[::-1],flags=cv2.INTER_LINEAR+cv2.WARP_INVERSE_MAP)
            imageObj.data = warpData
            imageObj.shape = warpData.shape
        self.imageShape[self.selectedWindow] = warpData.shape[:3]
        self.setImageRange()
        self.setViewBoxRangeLimits()
        self.displayImageInfo()
        self.displayImage()
    
    def copyPointsCheckboxCallback(self):
        pass
    
    def warpButtonCallback(self):
        pass


class ImageObj():
    
    def __init__(self,filePath,fileType,numCh,chFileOrg,loadData,autoColor):
        self.data = None
        self.alpha = 1
        self.alphaMap = None
        self.pixelSize = [None]*3
        self.position = None
        if isinstance(filePath,np.ndarray):
            self.fileType = 'data'
            self.filePath = None
            d = filePath
            self.data = self.formatData(filePath)
            self.shape = self.data.shape
            self.setAlphaMap(d)
        elif fileType=='Images (*.tif *.jpg *.png)':
            self.fileType = 'image'
            d = cv2.imread(filePath,cv2.IMREAD_ANYCOLOR)
            numCh = 3 if len(d.shape)>2 else 1
            self.filePath = [[filePath]]*numCh
            self.shape = d.shape[:2]+(1,numCh)
            if loadData: 
                self.data = d[:,:,None,::-1] if numCh==3 else d[:,:,None,None]
        elif fileType=='Image Series (*.tif *.jpg *.png)':
            self.fileType = 'image'
            self.filePath = [[] for _ in range(numCh)]
            for ind,file in enumerate(filePath):
                if ind==0:
                    d = cv2.imread(file,cv2.IMREAD_ANYCOLOR)
                    if chFileOrg=='rgb':
                        if len(d.shape)!=3:
                            raise Warning('Import aborted: images must be rgb if channel file organization is rgb')
                    elif len(d.shape)!=2:
                        raise Warning('Import aborted: images must be grayscale if channel file organization is not rgb')
                    numImg = len(filePath) if chFileOrg=='rgb' else int(len(filePath)/numCh)
                    self.shape = d.shape[:2]+(numImg,numCh)
                if chFileOrg=='rgb':
                    for ch in range(numCh):
                        self.filePath[ch].append(file)
                else:
                    ch = ind%numCh if chFileOrg=='alternating' else ind//int(len(filePath)/numCh)
                    self.filePath[ch].append(file)
            if loadData:
                self.data = self.getData()
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
            self.shape = (linesPerFrame,pixelsPerLine,numImg,numCh)
            zpos = []
            for frame in frames:
                zpos.append(float(frame.getElementsByTagName('SubindexedValue')[2].getAttribute('value')))
                for ch,tifFile in enumerate(frame.getElementsByTagName('File')):
                    file = os.path.join(os.path.dirname(filePath),tifFile.getAttribute('filename'))
                    self.filePath[ch].append(file)
            if loadData:
                self.data = self.getData()
            self.pixelSize = [round(float(pvStateValues[9].getElementsByTagName('IndexedValue')[0].getAttribute('value')),4)]*2
            if len(frames)>1:
                self.pixelSize.append(round(zpos[1]-zpos[0],4))
            else:
                self.pixelSize.append(None)
            xpos = float(pvStateValues[17].getElementsByTagName('SubindexedValue')[0].getAttribute('value'))
            ypos = float(pvStateValues[17].getElementsByTagName('SubindexedValue')[1].getAttribute('value'))
            self.position = [int(ypos/self.pixelSize[0]),int(xpos/self.pixelSize[1]),int(zpos[0]/self.pixelSize[2])] 
        elif fileType=='Numpy Array (*npy)':
            self.fileType = 'numpy'
            self.filePath = filePath
            d = np.load(filePath)
            numImg = d.shape[2] if len(d.shape)>2 else 1
            numCh = d.shape[3] if len(d.shape>3) else 1
            self.shape = d.shape[:2]+(numImg,numCh)
            self.setAlphaMap(data=d)
            if loadData:
                self.data = self.formatData(d)
        elif fileType=='Allen Atlas (*.nrrd)':
            self.fileType = 'atlas'
            self.filePath = filePath
            self.shape = (320,456,528,1)
            if loadData:
                self.data = self.getData()
            self.pixelSize = [25.0]*3
        self.levels = [[0,255] for _ in range(self.shape[3])]
        self.gamma = [1]*self.shape[3]
        self.rgbInd = [(0,1,2) for _ in range(self.shape[3])]
        if autoColor:
            for ch in range(self.shape[3])[:3]:
                self.rgbInd[ch] = (ch,)            
            
    def getData(self,channels=None,rangeSlice=None):
        # returns array with shape height x width x n x channels
        if channels is None:
            channels = list(range(self.shape[3]))
        if rangeSlice is None:
            rangeSlice = slice(0,self.shape[2])
        if self.data is None:
            if self.fileType=='image':
                chInd = channels
                imgInd = range(rangeSlice.start,rangeSlice.stop)
                data = np.zeros(self.shape[:2]+(len(imgInd),len(chInd)),dtype=np.uint8)
                for i,img in enumerate(imgInd):
                    for c,ch in enumerate(chInd):
                        d = cv2.imread(self.filePath[ch][img],cv2.IMREAD_ANYCOLOR)
                        if len(d.shape)>2:
                            data[:,:,i,:] = d[:,:,chInd[::-1]]
                            break
                        else:
                            data[:,:,i,c] = d
                return data
            elif self.fileType=='numpy':
                data = self.formatData(np.load(self.filePath))
            elif self.fileType=='atlas':
                data,_ = nrrd.read(self.filePath)
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
            data = None if self.fileType=='image' else self.getData(channels,rangeSlice)
        else:
            data = self.data
        for i in range(rangeSlice.start,rangeSlice.stop):
            for ch in channels:
                if data is None:
                    d = cv2.imread(self.filePath[ch][i],cv2.IMREAD_ANYCOLOR)
                    if len(d.shape)>2:
                        for c in channels[::-1]:
                            yield d[:,:,c]
                    else:
                        yield d
                else:
                    yield data[:,:,i,ch]
        
    def formatData(self,data):
        if data.dtype!='uint8':
            data = data.astype(float)
            data *= 255/np.nanmax(data)
            data.round(out=data)
            data = data.astype(np.uint8)
        if len(data.shape)<3:
            data = data[:,:,None,None]
        elif len(data.shape)<4:
            data = data[:,:,:,None]
        return data
        
    def setAlphaMap(self,data):
        if len(data.shape)<3:
            data = data[:,:,None]
        elif len(data.shape)>3:
            data = data[:,:,:,0]
        ind = np.isnan(data)
        if ind.any():
            self.alphaMap = np.zeros(self.shape[:3],dtype=np.uint8)
            self.alphaMap[np.logical_not(ind)] = 255
            
    def flipX(self):
        if self.data is None:
            pass
        else:
            self.data = self.data[:,::-1]
            
    def flipY(self):
        if self.data is None:
            pass
        else:
            self.data = self.data[::-1]
        
    def flipZ(self):
        if self.data is None:
            for chFiles in self.filePath:
                chFiles.reverse()
        else:
            self.data = self.data[:,:,::-1]
        
    def rotate90(self):
        if self.data is None:
            pass
        else:
            self.data = np.rot90(self.data)
                

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
        
def drawContour(image,threshold=255,lineWidth=-1):
    threshInd = image>=threshold
    image[threshInd] = 1
    image[np.logical_not(threshInd)] = 0
    _,contours,_ = cv2.findContours(image,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    maxContour = np.argmax([cont.shape[0] for cont in contours])
    cv2.drawContours(image,contours,maxContour,255,lineWidth)
    image[image<255] = 0
    return image


if __name__=="__main__":
    start()