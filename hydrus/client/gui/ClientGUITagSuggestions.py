import typing

from qtpy import QtCore as QC
from qtpy import QtWidgets as QW

from hydrus.core import HydrusConstants as HC
from hydrus.core import HydrusData
from hydrus.core import HydrusGlobals as HG
from hydrus.core import HydrusSerialisable
from hydrus.client import ClientConstants as CC
from hydrus.client.media import ClientMedia
from hydrus.client import ClientParsing
from hydrus.client import ClientSearch
from hydrus.client import ClientTags
from hydrus.client import ClientThreading
from hydrus.client.gui import ClientGUICommon
from hydrus.client.gui import ClientGUIDialogs
from hydrus.client.gui import ClientGUIListBoxes
from hydrus.client.gui import ClientGUIParsing
from hydrus.client.gui import QtPorting as QP

def FilterSuggestedPredicatesForMedia( predicates: typing.List[ ClientSearch.Predicate ], media: typing.Iterable[ ClientMedia.Media ], service_key: bytes ) -> typing.List[ ClientSearch.Predicate ]:
    
    tags = [ predicate.GetValue() for predicate in predicates ]
    
    filtered_tags = FilterSuggestedTagsForMedia( tags, media, service_key )
    
    predicates = [ predicate for predicate in predicates if predicate.GetValue() in filtered_tags ]
    
    return predicates
    
def FilterSuggestedTagsForMedia( tags: typing.List[ str ], media: typing.Iterable[ ClientMedia.Media ], service_key: bytes ) -> typing.List[ str ]:
    
    tags_filtered_set = set( tags )
    
    ( current_tags_to_count, deleted_tags_to_count, pending_tags_to_count, petitioned_tags_to_count ) = ClientMedia.GetMediasTagCount( media, service_key, ClientTags.TAG_DISPLAY_STORAGE )
    
    current_tags_to_count.update( pending_tags_to_count )
    
    num_media = len( media )
    
    for ( tag, count ) in current_tags_to_count.items():
        
        if count == num_media:
            
            tags_filtered_set.discard( tag )
            
        
    
    tags_filtered = [ tag for tag in tags if tag in tags_filtered_set ]
    
    return tags_filtered
    
class ListBoxTagsSuggestionsFavourites( ClientGUIListBoxes.ListBoxTagsStrings ):
    
    def __init__( self, parent, activate_callable, sort_tags = True ):
        
        ClientGUIListBoxes.ListBoxTagsStrings.__init__( self, parent, sort_tags = sort_tags )
        
        self._activate_callable = activate_callable
        
        width = HG.client_controller.new_options.GetInteger( 'suggested_tags_width' )
        
        if width is not None:
            
            self.setMinimumWidth( width )
            
        
    
    def _Activate( self ):
        
        if len( self._selected_terms ) > 0:
            
            tags = set( self._selected_terms )
            
            self._activate_callable( tags, only_add = True )
            
            self._RemoveSelectedTerms()
            
            self._DataHasChanged()
            
        
    
    def ActivateAll( self ):
        
        self._activate_callable( self.GetTags(), only_add = True )
        
    
    def TakeFocusForUser( self ):
        
        if len( self._selected_terms ) == 0 and len( self._terms ) > 0:
            
            self._Hit( False, False, 0 )
            
        
        self.setFocus( QC.Qt.OtherFocusReason )
        
    
class ListBoxTagsSuggestionsRelated( ClientGUIListBoxes.ListBoxTagsPredicates ):
    
    def __init__( self, parent, activate_callable ):
        
        ClientGUIListBoxes.ListBoxTagsPredicates.__init__( self, parent )
        
        self._activate_callable = activate_callable
        
        width = HG.client_controller.new_options.GetInteger( 'suggested_tags_width' )
        
        self.setMinimumWidth( width )
        
    
    def _Activate( self ):
        
        if len( self._selected_terms ) > 0:
            
            tags = { predicate.GetValue() for predicate in self._selected_terms }
            
            self._activate_callable( tags, only_add = True )
            
            self._RemoveSelectedTerms()
            
            self._DataHasChanged()
            
        
    
    def _GetTextFromTerm( self, term ):
        
        predicate = term
        
        return predicate.ToString( with_count = False )
        
    
    def TakeFocusForUser( self ):
        
        if len( self._selected_terms ) == 0 and len( self._terms ) > 0:
            
            self._Hit( False, False, 0 )
            
        
        self.setFocus( QC.Qt.OtherFocusReason )
        
    
class FavouritesTagsPanel( QW.QWidget ):
    
    def __init__( self, parent, service_key, media, activate_callable ):
        
        QW.QWidget.__init__( self, parent )
        
        self._service_key = service_key
        self._media = media
        
        vbox = QP.VBoxLayout()
        
        self._favourite_tags = ListBoxTagsSuggestionsFavourites( self, activate_callable, sort_tags = False )
        
        QP.AddToLayout( vbox, self._favourite_tags, CC.FLAGS_EXPAND_BOTH_WAYS )
        
        self.setLayout( vbox )
        
        self._UpdateTagDisplay()
        
    
    def _UpdateTagDisplay( self ):
        
        favourites = list( HG.client_controller.new_options.GetSuggestedTagsFavourites( self._service_key ) )
        
        ClientTags.SortTags( HC.options[ 'default_tag_sort' ], favourites )
        
        tags = FilterSuggestedTagsForMedia( favourites, self._media, self._service_key )
        
        self._favourite_tags.SetTags( tags )
        
    
    def MediaUpdated( self ):
        
        self._UpdateTagDisplay()
        
    
    def SetMedia( self, media ):
        
        self._media = media
        
        self._UpdateTagDisplay()
        
    
    def TakeFocusForUser( self ):
        
        self._favourite_tags.TakeFocusForUser()
        
    
class RecentTagsPanel( QW.QWidget ):
    
    def __init__( self, parent, service_key, media, activate_callable ):
        
        QW.QWidget.__init__( self, parent )
        
        self._service_key = service_key
        self._media = media
        
        self._last_fetched_tags = []
        
        self._new_options = HG.client_controller.new_options
        
        vbox = QP.VBoxLayout()
        
        clear_button = QW.QPushButton( 'clear', self )
        clear_button.clicked.connect( self.EventClear )
        
        self._recent_tags = ListBoxTagsSuggestionsFavourites( self, activate_callable, sort_tags = False )
        
        QP.AddToLayout( vbox, clear_button, CC.FLAGS_EXPAND_PERPENDICULAR )
        QP.AddToLayout( vbox, self._recent_tags, CC.FLAGS_EXPAND_BOTH_WAYS )
        
        self.setLayout( vbox )
        
        self._RefreshRecentTags()
        
    
    def _RefreshRecentTags( self ):
        
        def do_it( service_key ):
            
            def qt_code( recent_tags ):
                
                if not self or not QP.isValid( self ):
                    
                    return
                    
                
                self._last_fetched_tags = recent_tags
                
                self._UpdateTagDisplay()
                
                if len( self._recent_tags.GetTags() ) > 0:
                    
                    self._recent_tags.SelectTopItem()
                    
                
            
            recent_tags = HG.client_controller.Read( 'recent_tags', service_key )
            
            QP.CallAfter( qt_code, recent_tags )
            
        
        HG.client_controller.CallToThread( do_it, self._service_key )
        
    
    def _UpdateTagDisplay( self ):
        
        tags = FilterSuggestedTagsForMedia( self._last_fetched_tags, self._media, self._service_key )
        
        self._recent_tags.SetTags( tags )
        
    
    def EventClear( self ):
        
        from hydrus.client.gui import ClientGUIDialogsQuick
        
        result = ClientGUIDialogsQuick.GetYesNo( self, 'Clear recent tags?' )
        
        if result == QW.QDialog.Accepted:
            
            HG.client_controller.Write( 'push_recent_tags', self._service_key, None )
            
            self._last_fetched_tags = []
            
            self._UpdateTagDisplay()
            
        
    
    def RefreshRecentTags( self ):
        
        self._RefreshRecentTags()
        
    
    def MediaUpdated( self ):
        
        self._UpdateTagDisplay()
        
    
    def SetMedia( self, media ):
        
        self._media = media
        
        self._UpdateTagDisplay()
        
        self._RefreshRecentTags()
        
    
    def TakeFocusForUser( self ):
        
        self._recent_tags.TakeFocusForUser()
        
    
class RelatedTagsPanel( QW.QWidget ):
    
    def __init__( self, parent, service_key, media, activate_callable ):
        
        QW.QWidget.__init__( self, parent )
        
        self._service_key = service_key
        self._media = media
        
        self._last_fetched_predicates = []
        
        self._have_fetched = False
        
        self._new_options = HG.client_controller.new_options
        
        vbox = QP.VBoxLayout()
        
        self._button_2 = QW.QPushButton( 'medium', self )
        self._button_2.clicked.connect( self.EventSuggestedRelatedTags2 )
        self._button_2.setMinimumWidth( 30 )
        
        self._button_3 = QW.QPushButton( 'thorough', self )
        self._button_3.clicked.connect( self.EventSuggestedRelatedTags3 )
        self._button_3.setMinimumWidth( 30 )
        
        self._related_tags = ListBoxTagsSuggestionsRelated( self, activate_callable )
        
        button_hbox = QP.HBoxLayout()
        
        QP.AddToLayout( button_hbox, self._button_2, CC.FLAGS_EXPAND_SIZER_BOTH_WAYS )
        QP.AddToLayout( button_hbox, self._button_3, CC.FLAGS_EXPAND_SIZER_BOTH_WAYS )
        
        QP.AddToLayout( vbox, button_hbox, CC.FLAGS_EXPAND_PERPENDICULAR )
        QP.AddToLayout( vbox, self._related_tags, CC.FLAGS_EXPAND_BOTH_WAYS )
        
        self.setLayout( vbox )
        
    
    def _FetchRelatedTags( self, max_time_to_take ):
        
        def do_it( service_key, hash, search_tags, max_results, max_time_to_take ):
            
            def qt_code( predicates ):
                
                if not self or not QP.isValid( self ):
                    
                    return
                    
                
                self._last_fetched_predicates = predicates
                
                self._UpdateTagDisplay()
                
                self._have_fetched = True
                
            
            predicates = HG.client_controller.Read( 'related_tags', service_key, hash, search_tags, max_results, max_time_to_take )
            
            predicates = ClientSearch.SortPredicates( predicates )
            
            QP.CallAfter( qt_code, predicates )
            
        
        self._related_tags.SetPredicates( [] )
        
        ( m, ) = self._media
        
        hash = m.GetHash()
        
        search_tags = ClientMedia.GetMediasTags( self._media, self._service_key, ClientTags.TAG_DISPLAY_STORAGE, ( HC.CONTENT_STATUS_CURRENT, HC.CONTENT_STATUS_PENDING ) )
        
        max_results = 100
        
        HG.client_controller.CallToThread( do_it, self._service_key, hash, search_tags, max_results, max_time_to_take )
        
    
    def _QuickSuggestedRelatedTags( self ):
        
        max_time_to_take = self._new_options.GetInteger( 'related_tags_search_1_duration_ms' ) / 1000.0
        
        self._FetchRelatedTags( max_time_to_take )
        
    
    def _UpdateTagDisplay( self ):
        
        predicates = FilterSuggestedPredicatesForMedia( self._last_fetched_predicates, self._media, self._service_key )
        
        self._related_tags.SetPredicates( predicates )
        
    
    def EventSuggestedRelatedTags2( self ):
        
        max_time_to_take = self._new_options.GetInteger( 'related_tags_search_2_duration_ms' ) / 1000.0
        
        self._FetchRelatedTags( max_time_to_take )
        
    
    def EventSuggestedRelatedTags3( self ):
        
        max_time_to_take = self._new_options.GetInteger( 'related_tags_search_3_duration_ms' ) / 1000.0
        
        self._FetchRelatedTags( max_time_to_take )
        
    
    def MediaUpdated( self ):
        
        self._UpdateTagDisplay()
        
    
    def SetMedia( self, media ):
        
        self._media = media
        
        self._QuickSuggestedRelatedTags()
        
    
    def TakeFocusForUser( self ):
        
        self._related_tags.TakeFocusForUser()
        
    
class FileLookupScriptTagsPanel( QW.QWidget ):
    
    def __init__( self, parent, service_key, media, activate_callable ):
        
        QW.QWidget.__init__( self, parent )
        
        self._service_key = service_key
        self._media = media
        self._last_fetched_tags = []
        
        self._script_choice = ClientGUICommon.BetterChoice( self )
        
        self._script_choice.setEnabled( False )
        
        self._have_fetched = False
        
        self._fetch_button = ClientGUICommon.BetterButton( self, 'fetch tags', self.FetchTags )
        
        self._fetch_button.setEnabled( False )
        
        self._script_management = ClientGUIParsing.ScriptManagementControl( self )
        
        self._tags = ListBoxTagsSuggestionsFavourites( self, activate_callable, sort_tags = True )
        
        self._add_all = ClientGUICommon.BetterButton( self, 'add all', self._tags.ActivateAll )
        
        vbox = QP.VBoxLayout()
        
        QP.AddToLayout( vbox, self._script_choice, CC.FLAGS_EXPAND_PERPENDICULAR )
        QP.AddToLayout( vbox, self._fetch_button, CC.FLAGS_EXPAND_PERPENDICULAR )
        QP.AddToLayout( vbox, self._script_management, CC.FLAGS_EXPAND_PERPENDICULAR )
        QP.AddToLayout( vbox, self._add_all, CC.FLAGS_EXPAND_PERPENDICULAR )
        QP.AddToLayout( vbox, self._tags, CC.FLAGS_EXPAND_BOTH_WAYS )
        
        self._SetTags( [] )
        
        self.setLayout( vbox )
        
        self._FetchScripts()
        
    
    def _FetchScripts( self ):
        
        def do_it():
            
            def qt_code():
                
                if not self or not QP.isValid( self ):
                    
                    return
                    
                
                script_names_to_scripts = { script.GetName() : script for script in scripts }
                
                for ( name, script ) in list(script_names_to_scripts.items()):
                    
                    self._script_choice.addItem( script.GetName(), script )
                    
                
                new_options = HG.client_controller.new_options
                
                favourite_file_lookup_script = new_options.GetNoneableString( 'favourite_file_lookup_script' )
                
                if favourite_file_lookup_script in script_names_to_scripts:
                    
                    self._script_choice.SetValue( script_names_to_scripts[ favourite_file_lookup_script ] )
                    
                else:
                    
                    self._script_choice.setCurrentIndex( 0 )
                    
                
                self._script_choice.setEnabled( True )
                self._fetch_button.setEnabled( True )
                
            
            scripts = HG.client_controller.Read( 'serialisable_named', HydrusSerialisable.SERIALISABLE_TYPE_PARSE_ROOT_FILE_LOOKUP )
            
            QP.CallAfter( qt_code )
            
        
        HG.client_controller.CallToThread( do_it )
        
    
    def _SetTags( self, tags ):
        
        self._last_fetched_tags = tags
        
        self._UpdateTagDisplay()
        
    
    def _UpdateTagDisplay( self ):
        
        tags = FilterSuggestedTagsForMedia( self._last_fetched_tags, self._media, self._service_key )
        
        self._tags.SetTags( tags )
        
        if len( tags ) == 0:
            
            self._add_all.setEnabled( False )
            
        else:
            
            self._add_all.setEnabled( True )
            
        
    
    def FetchTags( self ):
        
        script = self._script_choice.GetValue()
        
        if script.UsesUserInput():
            
            message = 'Enter the custom input for the file lookup script.'
            
            with ClientGUIDialogs.DialogTextEntry( self, message ) as dlg:
                
                if dlg.exec() != QW.QDialog.Accepted:
                    
                    return
                    
                
                file_identifier = dlg.GetValue()
                
            
        else:
            
            ( m, ) = self._media
            
            file_identifier = script.ConvertMediaToFileIdentifier( m )
            
        
        stop_time = HydrusData.GetNow() + 30
        
        job_key = ClientThreading.JobKey( cancellable = True, stop_time = stop_time )
        
        self._script_management.SetJobKey( job_key )
        
        self._SetTags( [] )
        
        HG.client_controller.CallToThread( self.THREADFetchTags, script, job_key, file_identifier )
        
    
    def MediaUpdated( self ):
        
        self._UpdateTagDisplay()
        
    
    def SetMedia( self, media ):
        
        self._media = media
        
        self._UpdateTagDisplay()
        
    
    def TakeFocusForUser( self ):
        
        if self._have_fetched:
            
            self._tags.TakeFocusForUser()
            
        else:
            
            self._fetch_button.setFocus( QC.Qt.OtherFocusReason )
            
        
    
    def THREADFetchTags( self, script, job_key, file_identifier ):
        
        def qt_code( tags ):
            
            if not self or not QP.isValid( self ):
                
                return
                
            
            self._SetTags( tags )
            
            self._have_fetched = True
            
        
        parse_results = script.DoQuery( job_key, file_identifier )
        
        tags = ClientParsing.GetTagsFromParseResults( parse_results )
        
        QP.CallAfter( qt_code, tags )
        
    
class SuggestedTagsPanel( QW.QWidget ):
    
    def __init__( self, parent, service_key, media, activate_callable ):
        
        QW.QWidget.__init__( self, parent )
        
        self._service_key = service_key
        self._media = media
        
        self._new_options = HG.client_controller.new_options
        
        layout_mode = self._new_options.GetNoneableString( 'suggested_tags_layout' )
        
        self._notebook = None
        
        if layout_mode == 'notebook':
            
            self._notebook = ClientGUICommon.BetterNotebook( self )
            
            panel_parent = self._notebook
            
        else:
            
            panel_parent = self
            
        
        panels = []
        
        self._favourite_tags = None
        
        favourites = HG.client_controller.new_options.GetSuggestedTagsFavourites( self._service_key )
        
        if len( favourites ) > 0:
            
            self._favourite_tags = FavouritesTagsPanel( panel_parent, service_key, media, activate_callable )
            
            panels.append( ( 'favourites', self._favourite_tags ) )
            
        
        self._related_tags = None
        
        if self._new_options.GetBoolean( 'show_related_tags' ) and len( media ) == 1:
            
            self._related_tags = RelatedTagsPanel( panel_parent, service_key, media, activate_callable )
            
            panels.append( ( 'related', self._related_tags ) )
            
        
        self._file_lookup_script_tags = None
        
        if self._new_options.GetBoolean( 'show_file_lookup_script_tags' ) and len( media ) == 1:
            
            self._file_lookup_script_tags = FileLookupScriptTagsPanel( panel_parent, service_key, media, activate_callable )
            
            panels.append( ( 'file lookup scripts', self._file_lookup_script_tags ) )
            
        
        self._recent_tags = None
        
        if self._new_options.GetNoneableInteger( 'num_recent_tags' ) is not None:
            
            self._recent_tags = RecentTagsPanel( panel_parent, service_key, media, activate_callable )
            
            panels.append( ( 'recent', self._recent_tags ) )
            
        
        hbox = QP.HBoxLayout()
        
        if layout_mode == 'notebook':
            
            for ( name, panel ) in panels:
                
                self._notebook.addTab( panel, name )
                
            
            QP.AddToLayout( hbox, self._notebook, CC.FLAGS_EXPAND_BOTH_WAYS )
            
        elif layout_mode == 'columns':
            
            for ( name, panel ) in panels:
                
                QP.AddToLayout( hbox, panel, CC.FLAGS_EXPAND_PERPENDICULAR )
                
            
        
        self.setLayout( hbox )
        
        if len( panels ) == 0:
            
            self.hide()
            
        
    
    def MediaUpdated( self ):
        
        if self._favourite_tags is not None:
            
            self._favourite_tags.MediaUpdated()
            
        
        if self._recent_tags is not None:
            
            self._recent_tags.MediaUpdated()
            
        
        if self._file_lookup_script_tags is not None:
            
            self._file_lookup_script_tags.MediaUpdated()
            
        
        if self._related_tags is not None:
            
            self._related_tags.MediaUpdated()
            
        
    
    def SetMedia( self, media ):
        
        self._media = media
        
        if self._favourite_tags is not None:
            
            self._favourite_tags.SetMedia( media )
            
        
        if self._recent_tags is not None:
            
            self._recent_tags.SetMedia( media )
            
        
        if self._file_lookup_script_tags is not None:
            
            self._file_lookup_script_tags.SetMedia( media )
            
        
        if self._related_tags is not None:
            
            self._related_tags.SetMedia( media )
            
        
    
    def TakeFocusForUser( self, command ):
        
        if command == 'show_and_focus_manage_tags_favourite_tags':
            
            panel = self._favourite_tags
            
        elif command == 'show_and_focus_manage_tags_related_tags':
            
            panel = self._related_tags
            
        elif command == 'show_and_focus_manage_tags_file_lookup_script_tags':
            
            panel = self._file_lookup_script_tags
            
        elif command == 'show_and_focus_manage_tags_recent_tags':
            
            panel = self._recent_tags
            
        
        if panel is not None:
            
            if self._notebook is not None:
                
                self._notebook.SelectPage( panel )
                
            
            panel.TakeFocusForUser()
            
        
    
