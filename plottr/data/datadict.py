import numpy as np
import pandas as pd
import xarray as xr

class DataDict(dict):
    """
    Simple data storage class that is based on a regular dictionary.
    The basic structure of data looks like this:
        {
            'data_1' : {
                'axes' : ['ax1', 'ax2'],
                'unit' : 'some unit',
                'values' : [ ... ],
            },
            'ax1' : {
                'axes' : [],
                'unit' : 'some other unit',
                'values' : [ ... ],
            },
            'ax2' : {
                'axes' : [],
                'unit' : 'a third unit',
                'values' : [ ... ],
            },
            ...
        }
    I.e., we define data 'fields', that have unit, values, and we can specify that some data has axes
    (dependencies) specified by other data fields.

    For the data set to be valid:
    * the values of all fields have to have the same length.
    * all axes that are specified must exist as data fields.
    """

    # TODO: special class for griddata? get grid could return instance.

    def __init__(self, *arg, **kw):
        super().__init__(self, *arg, **kw)

    def __add__(self, newdata):
        s = self.structure()
        if s == newdata.structure():
            for k, v in self.items():
                val0 = self[k]['values']
                val1 = newdata[k]['values']
                if isinstance(val0, list) and isinstance(val1, list):
                    s[k]['values'] = self[k]['values'] + newdata[k]['values']
                else:
                    s[k]['values'] = np.append(np.array(self[k]['values']), np.array(newdata[k]['values']))
            return s
        else:
            raise ValueError('Incompatible data structures.')

    def append(self, newdata):
        if self.structure() == newdata.structure():
            for k, v in newdata.items():
                if isinstance(self[k]['values'], list) and isinstance(v['values'], list):
                    self[k]['values'] += v['values']
                else:
                    self[k]['values'] = np.append(np.array(self[k]['values']), np.array(v['values']))

    def structure(self):
        if self.validate():
            s = {}
            for n, v in self.items():
                s[n] = dict(axes=v['axes'], unit=v['unit'])
            return s

    def label(self, name):
        if self.validate():
            if name not in self:
                raise ValueError("No field '{}' present.".format(name))

            n = name
            if self[name]['unit'] != '':
                n += ' ({})'.format(self[name]['unit'])

            return n

    def dependents(self):
        if self.validate():
            ret = []
            for n, v in self.items():
                if len(v.get('axes', [])) != 0:
                    ret.append(n)
            return ret

    def validate(self):
        nvals = None
        nvalsrc = None
        msg = '\n'
        for n, v in self.items():
            if 'axes' in v:
                for na in v['axes']:
                    if na not in self:
                        msg += " * '{}' has axis '{}', but no data with name '{}' registered.\n".format(n, na, na)
            else:
                v['axes'] = []

            if 'unit' not in v:
                v['unit'] = ''

            if 'values' not in v:
                v['values'] = []

            if nvals is None:
                nvals = len(v['values'])
                nvalsrc = n
            else:
                if len(v['values']) != nvals:
                    msg += " * '{}' has length {}, but have found {} in '{}'\n".format(n, len(v['values']), nvals, nvalsrc)

        if msg != '\n':
            raise ValueError(msg)

        return True

    def _value_dict(self, use_units=False):
        if self.validate():
            ret = {}
            for k, v in self.items():
                name = k
                if use_units and v['unit'] != '':
                    name += ' ({})'.format(v['unit'])
                ret[name] = v['values']

            return ret

    def to_dataframe(self):
        return pd.DataFrame(self._value_dict())

    def to_multiindex_dataframes(self, use_units=False):
        if self.validate():
            dfs = {}
            for n, v in self.items():
                if not len(v['axes']):
                    continue

                vals = v['values']
                axvals = []
                axnames = []
                for axname in v['axes']:
                    axvals.append(self[axname]['values'])
                    _axname = axname
                    if use_units and self[axname]['unit'] != '':
                        _axname += ' ({})'.format(self[axname]['unit'])
                    axnames.append(_axname)

                mi = pd.MultiIndex.from_tuples(list(zip(*axvals)), names=axnames)

                _name = n
                if use_units and self[n]['unit'] != '':
                    _name += ' ({})'.format(self[n]['unit'])
                df = pd.DataFrame({_name : v['values']}, mi)
                dfs[n] = df

            return dfs

    def to_xarray(self, name):
        df = self.to_multiindex_dataframes()[name]
        arr = xr.DataArray(df)

        for idxn in arr.indexes:
            idx = arr.indexes[idxn]

            if idxn not in self:
                if isinstance(idx, pd.MultiIndex):
                    arr = arr.unstack(idxn)
                else:
                    arr = arr.squeeze(idxn).drop(idxn)

        return arr

    def get_grid(self, name=None, mask_nan=True):
        if name is None:
            name = self.dependents()
        if isinstance(name, str):
            name = [name]

        for n in name:
            arr = self.to_xarray(n)

            ret = {}
            for idxn in arr.indexes:
                vals = arr.indexes[idxn].values

                if idxn in ret and vals.shape != ret[idxn]['values'].shape:
                    raise ValueError(
                        "'{}' used in different shapes. Arrays cannot be used as data and axis in a single grid data set.".format(idxn)
                    )

                ret[idxn] = dict(
                    values=vals,
                    unit=self[idxn]['unit']
                    )

            if mask_nan and len(np.where(np.isnan(arr.values))[0]) > 0:
                v = np.ma.masked_where(np.isnan(arr.values), arr.values)
            else:
                v = arr.values
            ret[n] = dict(
                values=v,
                axes=self[n]['axes'],
                unit=self[n]['unit'],
                )

        return
