'''
    ...

    Author: Higor S. Monteiro
    Email: higor.monteiro@fisica.ufc.br
'''

# -- lib
import numpy as np
import pandas as pd
import datetime as dt
from simpledbf import Dbf5

from sqlalchemy import create_engine
from sqlalchemy import Column, Table, MetaData
from sqlalchemy import select, insert, update, delete
from sqlalchemy import inspect, text
from sqlalchemy import DateTime, Integer, Numeric, String, Sequence, ForeignKey, CheckConstraint
from sqlalchemy.exc import InternalError, IntegrityError

# -- utility class
class smart_dict(dict):
    def __missing__(self, x):
        if pd.notna(x):
            return x
        return None
    
class WarehouseBase:
    '''
        Data warehouse to store personal and extra identification from DATASUS databases.
        
        To assist the procedures of data matching within and between specific databases originated
        from DATASUS information systems, this class manages the storage through CRUD operations
        on individual records. Main information identifying individuals in the original data are stored
        for proper data matching (linkage). Extra information can also be stored for further reporting
        pipelines.
        
        Args:
        -----
            engine_url:
                String. Absolute path to the warehouse database.
                
        Attributes:
        -----------
            tables:
                Dictionary. Following a key-value schema, it stores the SQLALCHEMY data models defined for 
                the database. Keys refer to the specific data models names. 
            mappings:
                Dictionary. Following a key-value schema, it stores the field relations between the original
                data source and the schema used in the data models. 
    '''
    def __init__(self, engine_url):
        self._engine = create_engine(engine_url, future=True)
        self._metadata = MetaData()
        self._tables = {}
        self._mappings = {}

        # -- include the data models
        self._imported_data_models = []

        for elem in self._imported_data_models:
            self._tables.update(elem[0])
            self._mappings.update(elem[1])    

    # ------------------ custom properties ------------------
    @property
    def engine(self):
        return self._engine
    
    @engine.setter
    def engine(self, v):
        raise Exception()
    
    @property
    def tables(self):
        return self._tables
    
    @tables.setter
    def tables(self, v):
        raise Exception()
    
    @property
    def mappings(self):
        return self._mappings
    
    @mappings.setter
    def mappings(self, v):
        raise Exception()
        
    @property
    def metadata(self):
        return self._metadata
    
    @metadata.setter
    def metadata(self, v):
        raise Exception()
    
    # ------------------ lazy connection with the database ------------------

    def db_init(self):
        self._metadata.create_all(self._engine)
        return self._engine

    # ------------------ expected column names for each table ------------------

    def expected_columns(self):
        data_models = [ table_model_dict[0] for table_model_dict in self._imported_data_models ]
        expected_cols_models = { list(model.keys())[0] : [ col.name for col in list(model.values())[0].columns] for model in data_models }
        return expected_cols_models
    
    # ------------------ CRUD ------------------

    def insert(self, table_name, data_df, batchsize=50, verbose=True):
        '''
            Insert new records from a given dataframe.
            
            Args:
            -----
                table_name:
                    String. Table name inside the database. Possible to extract
                    from attribute 'tables'.
                data_df:
                    pandas.DataFrame. Records to be inserted. Schema should match the 
                    official data sources. For instance, if the data source is SIVEP-Gripe,
                    then the columns must match the original ones. 
                batchsize:
                    Integer. Size of the batches of records to insert in the table.
        '''
        # -- load the data model and the schema mapping from 'table_name' and rename the columns of 'data_df'
        try:
            table_model, table_mapping = self._tables[table_name], self._mappings[table_name]
        except:
            raise Exception(f"Table '{table_name}' not found.")
        try:
            data_df = data_df.rename(table_mapping, axis=1, errors='raise')
        except:
            raise Exception('Data source schema could not be properly mapped.')
        
        # - define 'smart_hash' to avoid 'NaN' values in the records during insert
        nonan_hash = smart_dict()

        # -- perform batch insertion of records into the table.
        data_df = data_df[ table_mapping.values() ]
        splitted_data = np.split(data_df, np.arange(batchsize, data_df.shape[0]+1, batchsize))
        for nindex, current_batch in enumerate(splitted_data):
            has_duplicate = False
            if verbose:
                print(f'Insertion of batch {nindex+1} of {len(splitted_data)} ... ', end='')
            
            # - format records to be inserted
            records = [ { field : nonan_hash[val] for field, val in btc.items() } for btc in current_batch.to_dict(orient='records')]
            if len(records)==0 and verbose: 
                print('no records ... done.')
                continue
        
            # -- insert batch
            try:
                ins = table_model.insert()
                with self._engine.connect() as conn:
                    rp = conn.execute(ins, records)
                    conn.commit()
            except IntegrityError as error:
                if verbose:
                    print(f'error: {error.args[0]} ... ', end='')
                
                # -- if there are duplicates, add one by one
                if 'UNIQUE constraint failed:' in error.args[0]:
                    if verbose:
                        print(f'adding one by one ... ', end='')
                
                    for cur_record in records:
                        new_ins = table_model.insert()
                        try:
                            with self._engine.connect() as conn:
                                rp = conn.execute(new_ins, cur_record)
                                conn.commit()
                        except:
                            continue
                    
            if verbose:
                print('done.')
        
    def update(self, table_name, primary_key_value, updated_record, verbose=True):
        '''
            Update a given record identified by its primary key value 'primary_key_value'.
            
            Args:
            -----
                table_name:
                    String. Table name inside the database. Possible to extract
                    from attribute 'tables'.
                primary_key_value:
                    String. Identifier value in the primary key field for update.
                updated_record:
                    Dictionary. Dictionary matching the table schema with the updated 
                    value.
        '''
        # -- load the data model and define update filtering
        table_model = self._tables[table_name]
        primary_key_name = [ p.name for p in inspect(table_model).primary_key ][0]
        updt = update(table_model).where(table_model.c[primary_key_name] == primary_key_value)
        updt = updt.values(updated_record)
        if verbose:
            print(f'Update query: {updt} ...', end='')
        
        try:
            with self._engine.connect() as conn:
                rp = conn.execute(updt)
                conn.commit()
        except IntegrityError as error:
            print(f'error: {error.args[0]}', end='')
        
        if verbose:
            print(' done.')

    def delete(self, table_name, list_of_records, verbose=True):
        '''
            Delete a list of records from the warehouse. The records are identified
            according to the value of their primary keys.
            
            Args:
            -----
                table_name:
                    String. Table name inside the database. Possible to extract
                    from attribute 'tables'.
                list_of_records:
                    List of unique IDs representing the primary key of the records 
                    to be deleted.
        '''
        # - Load the data model and extract the name of its primary key
        table_model = self._tables[table_name]
        primary_key_name = [ p.name for p in inspect(table_model).primary_key ][0]
        
        if list_of_records:
            for nindex, current_rec in enumerate(list_of_records):
                if verbose:
                    print(f'Deletion of record {current_rec} ({nindex+1}/{len(list_of_records)}) ... ', end='')
                
                try:
                    qdel = delete(table_model).where(table_model.c[primary_key_name]==current_rec)
                    with self._engine.connect() as conn:
                        rp = conn.execute(qdel)
                        conn.commit()
                except IntegrityError as error:
                    if verbose:
                        print(f'error: {error.args[0]}', end='')
                
                if verbose:
                    print('done.')

    def delete_table(self, table_name, is_sure=False, authkey=""):
        '''
            Delete a given table from the database.
            
            Args:
            -----
                table_name:
                    String. Table name inside the database. Possible to extract
                    from attribute 'tables'.
                is_sure:
                    Bool. To delete table, it must be parsed as True.
                pkey:
                    String. To delete table, it must be assigned to the correct string. For
                    now, it avoids accidental deletions.
        '''
        sql_str = f"DROP TABLE IF EXISTS {table_name};"
        sql_query = text(sql_str)
        with self._engine.connect() as conn:
            if is_sure and authkey=="###!Y!.":
                rp = conn.execute(sql_query)
                conn.commit()

                _temp = self._tables.pop(table_name)
                _temp = self._mappings.pop(table_name)
            else:
                raise Exception('delete table command called, but without assurance.')
            
    # --------------- BUILT-IN QUERY METHODS ---------------
    
    def number_of_records(self, table_name):
        '''
            Return the number of records from a specific table within the warehouse.
            
            Args:
            -----
                table_name:
                    String. Table name inside the database. Possible to extract
                    from attribute 'tables'.
    
            Results:
                results:
                    Integer. Number of records queried from the database. 
        '''
        # -- Load and select the data model
        table_model = self._tables[table_name]
        sel = select(table_model)

        try:
            with self._engine.connect() as conn:
                rp = conn.execute(sel)
                nrecords = 0
                for record in rp: nrecords+=1
                return nrecords
        except Exception as error:
            print(error.args[0])
            return -1
    
    def query_all(self, table_name):
        '''
            Select records from a specific table within the warehouse.
            
            Args:
            -----
                table_name:
                    String. Table name inside the database. Possible to extract
                    from attribute 'tables'.
    
            Results:
                results:
                    List. List of sql table rows queried from the database. 
        '''
        # -- load and select the data model
        table_model = self._tables[table_name]
        sel = select(table_model)

        try:
            with self._engine.connect() as conn:
                rp = conn.execute(sel)
                results = [ record for record in rp ]
                return results
        except Exception as error:
            print(error.args[0])
            return []
    
    def query_where(self, table_name, value=None, colname=None, condition='equal'):
        '''
            Select records matching a specific value of a field in the table.
            
            Args:
            -----
                table_name:
                    String. Table name inside the database. Possible to extract
                    from attribute 'tables'.
                value:
                    Base. Value to be matched in the given field.
                colname:
                    String. Column of the table used for ordering and filtering.
                    If not provided, the query will return all records from the table.
                    
            Results:
                results:
                    List. List of sql table rows queried from the database. 
        '''
        if colname is None:
            return self.query_all(table_name)
        
        # -- select the data model and build the query
        table_model = self._tables[table_name]
        sel = select(table_model)
        if condition=='equal':
            sel = sel.where(table_model.c[colname] == value)
        if condition=='larger':
            sel = sel.where(table_model.c[colname] >= value)
        elif condition=='smaller':
            sel = sel.where(table_model.c[colname] < value)
        
        sel = sel.order_by(table_model.c[colname])
                
        # -- try to perform query
        try:
            with self._engine.connect() as conn:
                rp = conn.execute(sel)
                results = [ record for record in rp ]
                return results
        except Exception as error:
            print(error.args[0])
            return []
    
    def query_period(self, table_name, date_col=None, period=None):
        '''
            Select records from a specific table within the warehouse.
            
            Args:
            -----
                table_name:
                    String. Table name inside the database. Possible to extract
                    from attribute 'tables'.
                date_col:
                    String. Column date of the table used for ordering and filtering
                    by period (if 'period' is provided).
                period:
                    2-element list of datetime.datetime. Starting and ending dates of the period
                    selected for the query. This period is applied over the column name
                    parsed to 'date_col' variable. If the end date is not provided, then
                    datetime.datetime.today() is used.
                    
            Results:
                results:
                    List. List of sql table rows queried from the database. 
        '''
        period = list(period)
        if date_col is None:
            raise Exception("The name of the datetime field should be provided.")
        
        # -- select the data model and build the query
        table_model = self._tables[table_name]
        sel = select(table_model)
        sel = sel.order_by(table_model.c[date_col])
        if period is not None:
            if period[1] is None:
                period[1] = dt.datetime.today()
            sel = sel.where(table_model.c[date_col].between(period[0], period[1]))
                
        # -- try to perform query
        try:
            with self._engine.connect() as conn:
                rp = conn.execute(sel)
                results = [ record for record in rp ]
                return results
        except Exception as error:
            print(error.args[0])
            return []
        
    def query_id(self, table_name, year, date_col='DATA_NOTIFICACAO'):
        '''
            Select the records' IDs from a specific period within the warehouse.
            
            Args:
            -----
                table_name:
                    String. Table name inside the database. Possible to extract from
                    'self._tables'.
                year:
                    Integer. 
                date_col:
                    String. Column date of the table used for ordering and filtering
                    by period (if 'period' is provided).
                    
            Return:
            -------
                results:
                    List. List of sql table rows queried from the database. 
        '''
        # -- load and select the data model
        try:
            table_model = self._tables[table_name]
        except:
            raise Exception(f"Table '{table_name}' not found.")
        
        primary_key_name = [ p.name for p in inspect(table_model).primary_key ][0]
        sel = select(table_model.c[primary_key_name], table_model.c[date_col]).where(table_model.c[date_col].between(dt.datetime(year, 1, 1), dt.datetime(year, 12, 31)))
                
        # -- try to perform query
        try:
            with self._engine.connect() as conn:
                rp = conn.execute(sel)
                results = [ record for record in rp ]
                return results
        except Exception as error:
            print(error.args[0])
            return [] 