# -*- coding: utf-8 -*-
import os
from pathlib import Path
import ftplib
import datetime as dt
from ftplib import FTP 

from simpledbf import Dbf5
from pyopensus.utils.DBFIX import DBFIX
import pyopensus.utils.utils as utils

class Opensus:
    '''
        Simple interface to download open source health data from DATASUS 
        using their FTP protocol. 
    '''
    def __init__(self) -> None:
        self._host = 'ftp.datasus.gov.br'
        self.baseftp = FTP(self._host)
        self.baseftp.login()
        self.basepath = '/dissemin/publicos/'
        
        self.sys_included = {'sihsus': self.basepath+'SIHSUS/200801_/Dados/',
                             'sihsus_1992_2007': self.basepath+'SIHSUS/199201_200712/Dados/', 
                             'siasus': self.basepath+'SIASUS/200801_/Dados/',
                             'siasus_1994_2007': self.basepath+'SIASUS/199401_200712/Dados/', 
                             'sim': self.basepath+'SIM/CID10/DORES/',
                             'sinasc': self.basepath+'SINASC/1996_/Dados/DNRES/',
                             'cnes': self.basepath+'CNES/200508_/Dados/',
                             'sinan': self.basepath+'SINAN/DADOS/FINAIS/',
                             'sinan_prelim': self.basepath+'SINAN/DADOS/PRELIM/',
                             'painel_oncologia': self.basepath+'painel_oncologia/Dados/',
                             'pni': self.basepath+'PNI/DADOS/'}
        
        self.base_error = ftplib.all_errors[1]
        
    def reconnect_if_needed(self):
        try:
            self.baseftp.pwd()
        except self.base_error as err:
            self.baseftp = FTP(self._host)
            self.baseftp.login()

    def preffix_dictionary(self, origin : str):
        '''
            Descriptions of available preffixes for a given source.
        '''
        preffix_hash = utils.preffix_dictionary()

        if origin.lower() in preffix_hash.keys():
            return preffix_hash[origin]
    
    # ---------------------------------------
    # -- hide host string from the interface.
    @property
    def host(self):
        return self.host
    
    @host.setter
    def host(self, v):
        raise Exception('No change allowed for host string.')
        
    def get_sources(self):
        '''
            List the sources available for download using the interface.
        '''
        return list(self.sys_included.keys())

    
    def listdir(self, origin=None):
        '''
            List the files and folder of a specific directory within the host FTP.

            Args:
            -----
                origin:
                    String {default = None}. Name of the folder where to list the
                    files. If None, lists the files in the home folder.
        '''
        self.reconnect_if_needed()

        if origin is None:
            self.baseftp.cwd('/dissemin/publicos/')
            self.baseftp.retrlines('LIST')
        else:
            if origin.lower() in self.sys_included.keys():
                self.baseftp.cwd(self.sys_included[origin.lower()])
                self.baseftp.retrlines('LIST')

    def retrieve_file(self, dest:str, origin:str, filename:str, preffix_folder=None, to_dbf=False, to_parquet=False, verbose=False):
        '''
            Download data based on the filename and origin from one of the allowed sources.

            Args:
            -----
                dest:
                    String. Output folder.
                origin:
                    String. DATASUS source of the requested data. Examples of sources are: SIHSUS, SINAN, SIM, etc.
                    A list of available sources can be displayed by calling Opensus.get_sources().
                filename:
                    String. Name of the file without extension.
                preffix:
                    String. Preffix string referring to the type of the data stored for the system. 
                    For instance, CNES data is stored in different folders for each preffix. So, a preffix
                    is needed in order to retrieve file.
                to_dbf:
                    Bool. Whether downloaded .DBC file must be converted to DBF.
                to_parquet:
                    Bool. Active only when 'to_dbf=True'. Whether downloaded .DBF file must be converted to PARQUET.
                verbose:
                    Bool. Verbose.

            Return:
            -------
                None.
        '''
        self.reconnect_if_needed()
        # -- check whether the source is supported.
        if origin.lower() not in self.sys_included.keys():
            raise Exception('System source not supported.')
        else:
            self.baseftp.cwd(self.sys_included[origin.lower()])

        if preffix_folder is not None:
            self.baseftp.cwd(preffix_folder)

        # -- create folders (if they do not exist)
        if not os.path.isdir(os.path.join(dest, "DBC")):
            os.mkdir(os.path.join(dest, "DBC"))
        if not os.path.isdir(os.path.join(dest, "DBF")):
            os.mkdir(os.path.join(dest, "DBF"))
        if to_parquet and not os.path.isdir(os.path.join(dest, "PARQUET")):
            os.mkdir(os.path.join(dest, "PARQUET"))

        filename_ = Path(filename).stem
        filename_dbc, filename_dbf = f'{filename_}.dbc', f'{filename_}.dbf'

        if verbose:
            print(f'Download do arquivo {filename_dbc} ...', end='')
            
        # -- FTP download.
        with open(os.path.join(dest, "DBC", filename_dbc), 'wb') as fp:
            self.baseftp.retrbinary(f'RETR {filename_dbc}', fp.write)
                
        # -- conversion of DBC file to a DBF file.
        if to_dbf:
            path_to_dbc = os.path.join(dest, "DBC", filename_dbc)
            path_to_dbf = os.path.join(dest, "DBF", filename_dbf)
            utils.dbc2dbf(path_to_dbc, path_to_dbf)

            # -- conversion of DBF file to a PARQUET file (memory-efficient format).
            if to_parquet:
                temp_df = Dbf5(os.path.join(dest, "DBF", filename_dbf), codec='latin').to_dataframe()
                temp_df.to_parquet(os.path.join(dest, "PARQUET", filename_+'.parquet'))

        if verbose:
            print(' Feito.')

    
    # -- global function to handle calls
    def retrieve_year(self, dest:str, origin:str, uf:str, year:int, preffix="RD", to_dbf=False, verbose=False):
        '''
            Download data for a given year from one of the allowed sources.

            Args:
            -----
                dest:
                    String. Output folder.
                origin:
                    String. Source of the requested data.
                uf:
                    String. UF string for a brazilian state.
                year:
                    Integer. Year referring to the requested data. 
                preffix:
                    String. Preffix string referring to the type of the data stored
                    for the system. For example, if a reduced AIH from SIHSUS is requested, 
                    then the preffix should be 'RD'.
                to_dbf:
                    Bool. Whether downloaded .DBC file must be converted to DBF.
                verbose:
                    Bool. Verbose.

            Return:
            -------
                None.
        '''
        self.reconnect_if_needed()

        # -- check whether the source is supported.
        if origin.lower() not in self.sys_included.keys():
            raise Exception('System source not supported.')
        else:
            self.baseftp.cwd(self.sys_included[origin.lower()])
        
        # -- create folders
        if not os.path.isdir(os.path.join(dest, "DBC")):
            os.mkdir(os.path.join(dest, "DBC"))
        if not os.path.isdir(os.path.join(dest, "DBF")):
            os.mkdir(os.path.join(dest, "DBF"))

        # -- specify calls
        if origin.lower()=='siasus' or origin.lower()=='sihsus':
            utils.retrieve_siasih(self.baseftp, dest, uf, year, preffix, to_dbf, verbose)
        elif origin.lower()=='sinasc' or origin.lower()=='sim':
            print('...')
            utils.retrieve_vital(self.baseftp, dest, origin.lower(), uf, year, to_dbf, verbose)
        elif origin.lower()=='cnes':
            utils.retrieve_cnes(self.baseftp, dest, uf, year, preffix, to_dbf, verbose)
        elif origin.lower()=='sinan':
            utils.retrieve_sinan(self.baseftp, dest, year, preffix, to_dbf, verbose)
        else:
            pass
            
