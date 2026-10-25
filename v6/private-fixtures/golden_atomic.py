import pluggy
Original=pluggy.PluginManager
class Golden(Original):
 def register(self,plugin,name=None):
  names=dict(self._name2plugin);attrs=dict(vars(self.hook));impls={key:list(value.get_hookimpls()) for key,value in attrs.items() if hasattr(value,'get_hookimpls')}
  try:return super().register(plugin,name)
  except BaseException:
   self._name2plugin.clear();self._name2plugin.update(names)
   for key in list(vars(self.hook)):
    if key not in attrs:delattr(self.hook,key)
   for key,values in impls.items():getattr(self.hook,key)._hookimpls[:]=values
   raise
pluggy.PluginManager=Golden
