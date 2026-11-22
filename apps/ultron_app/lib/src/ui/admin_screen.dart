import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import '../domain/access.dart';
import '../domain/models.dart';
import '../state/providers.dart';
import 'components.dart';

class AdminScreen extends ConsumerStatefulWidget {
  const AdminScreen({super.key,this.rolesOnly=false});
  final bool rolesOnly;
  @override
  ConsumerState<AdminScreen> createState()=>_AdminScreenState();
}
class _AdminScreenState extends ConsumerState<AdminScreen> {
  final _search=TextEditingController();
  List<AccessRole> _roles=[];
  UserPage? _users;
  String? _error;
  bool _loading=true;
  int _page=0,_request=0;
  @override
  void initState(){super.initState();_load();}
  @override
  void dispose(){_search.dispose();super.dispose();}
  Future<void> _load() async {
    final request=++_request;
    setState((){_loading=true;_error=null;});
    try{
      final repository=ref.read(repositoryProvider);
      final roles=await repository.listRoles();
      final users=widget.rolesOnly ? null : await repository.listUsers(search:_search.text.trim(),page:_page);
      if(mounted && request==_request) setState((){_roles=roles;_users=users;});
    } on FrontendException catch(error){if(mounted && request==_request) setState(()=>_error=error.message);}
    catch(_){if(mounted && request==_request) setState(()=>_error='User management is unavailable. Try again.');}
    finally{if(mounted && request==_request) setState(()=>_loading=false);}
  }
  @override
  Widget build(BuildContext context)=>PageBody(maxWidth:1060,children:[
    PageHeading(widget.rolesOnly?'Roles & permissions':'User management',subtitle:widget.rolesOnly?'Decide what each role can do in the app and agent.':'Create accounts, review registrations, assign roles and suspend access.'),
    Wrap(spacing:10,runSpacing:10,children:[
      if(canAccess(ref,'users.manage')) OutlinedButton.icon(onPressed:()=>context.go('/app/admin'),icon:const Icon(LucideIcons.users,size:17),label:const Text('Users')),
      if(canAccess(ref,'roles.manage')) OutlinedButton.icon(onPressed:()=>context.go('/app/roles'),icon:const Icon(LucideIcons.shieldCheck,size:17),label:const Text('Roles & permissions')),
      if(!widget.rolesOnly && canAccess(ref,'users.manage')) FilledButton.icon(onPressed:_createUser,icon:const Icon(LucideIcons.userPlus,size:17),label:const Text('Create user')),
      if(widget.rolesOnly && canAccess(ref,'roles.manage')) FilledButton.icon(onPressed:()=>_editRole(),icon:const Icon(LucideIcons.plus,size:17),label:const Text('Create role')),
      IconButton(onPressed:_loading?null:_load,tooltip:'Refresh access records',icon:const Icon(LucideIcons.refreshCw,size:19)),
    ]),
    const SizedBox(height:20),
    const NotePanel('New registrations have no app or agent access. Verify the person’s identity before activating an account. Saving access changes ends affected sessions immediately.'),
    const SizedBox(height:20),
    if(!widget.rolesOnly) TextField(controller:_search,onSubmitted:(_){_page=0;_load();},decoration:InputDecoration(hintText:'Search users by name or email',prefixIcon:const Icon(LucideIcons.search,size:18),suffixIcon:IconButton(tooltip:'Search users',onPressed:(){_page=0;_load();},icon:const Icon(LucideIcons.arrowRight,size:18)))),
    const SizedBox(height:18),
    if(_loading) const Center(child:Padding(padding:EdgeInsets.all(32),child:CircularProgressIndicator()))
    else if(_error!=null) ...[NotePanel(_error!,warning:true),TextButton(onPressed:_load,child:const Text('Try again'))]
    else if(widget.rolesOnly) ...[
      for(final role in _roles) Card(child:Padding(padding:const EdgeInsets.all(18),child:Row(crossAxisAlignment:CrossAxisAlignment.start,children:[
        const Padding(padding:EdgeInsets.only(top:3,right:14),child:Icon(LucideIcons.shield,size:21)),
        Expanded(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(role.name,style:Theme.of(context).textTheme.titleMedium),const SizedBox(height:5),Text(role.immutable?'Protected system role':'${role.permissions.length} permissions',style:Theme.of(context).textTheme.bodySmall),const SizedBox(height:10),Wrap(spacing:6,runSpacing:6,children:role.permissions.map((p)=>Chip(label:Text(accessPermissions[p]??p,style:const TextStyle(fontSize:11)))).toList())])),
        IconButton(tooltip:role.immutable?'Protected role':'Edit ${role.name}',onPressed:role.immutable?null:()=>_editRole(role),icon:Icon(role.immutable?LucideIcons.lockKeyhole:LucideIcons.pencil,size:18)),
      ]))),
    ] else ...[
      if(_users!.users.isEmpty) const Padding(padding:EdgeInsets.all(25),child:Text('No registrations match your search.')),
      for(final user in _users!.users) Card(child:Padding(padding:const EdgeInsets.all(18),child:Row(crossAxisAlignment:CrossAxisAlignment.start,children:[
        CircleAvatar(child:Text(user.name.isEmpty?'?':user.name.substring(0,1).toUpperCase())),const SizedBox(width:14),
        Expanded(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(user.name,style:Theme.of(context).textTheme.titleMedium),const SizedBox(height:3),Text(user.email),const SizedBox(height:8),Wrap(spacing:8,runSpacing:5,children:[Chip(label:Text(user.status)),Chip(label:Text(user.roleName))]),const SizedBox(height:5),Text(user.emailVerified?'Email verified':'Email ownership not verified',style:Theme.of(context).textTheme.bodySmall)])),
        IconButton(tooltip:'Manage ${user.name}',onPressed:()=>_editUser(user),icon:const Icon(LucideIcons.pencil,size:18)),
      ]))),
      const SizedBox(height:12),
      Row(mainAxisAlignment:MainAxisAlignment.spaceBetween,children:[TextButton(onPressed:_page>0?(){_page--;_load();}:null,child:const Text('Previous')),Text('Page ${_page+1}'),TextButton(onPressed:_users!.hasMore?(){_page++;_load();}:null,child:const Text('Next'))]),
    ],
  ]);

  Future<void> _editUser(AppUser user) async {
    var status=user.status,roleId=user.roleId,busy=false,verified=false;
    String? error;
    final changed=await showDialog<bool>(context:context,builder:(dialogContext)=>StatefulBuilder(builder:(context,setDialogState)=>AlertDialog(
      title:Text('Access for ${user.name}'),
      content:SizedBox(width:440,child:SingleChildScrollView(child:Column(mainAxisSize:MainAxisSize.min,crossAxisAlignment:CrossAxisAlignment.stretch,children:[
        Text(user.email),const SizedBox(height:20),
        DropdownButtonFormField<String>(initialValue:status,isExpanded:true,decoration:const InputDecoration(labelText:'Account status'),items:['pending','active','disabled'].map((s)=>DropdownMenuItem(value:s,child:Text(s))).toList(),onChanged:busy?null:(v)=>setDialogState(()=>status=v!)),
        const SizedBox(height:18),DropdownButtonFormField<String>(initialValue:roleId,isExpanded:true,decoration:const InputDecoration(labelText:'Role'),items:_roles.map((r)=>DropdownMenuItem(value:r.id,child:Text(r.name,overflow:TextOverflow.ellipsis))).toList(),onChanged:busy?null:(v)=>setDialogState(()=>roleId=v!)),
        const SizedBox(height:18),
        if(status=='active' && user.status!='active') CheckboxListTile(contentPadding:EdgeInsets.zero,value:verified,onChanged:busy?null:(v)=>setDialogState(()=>verified=v!),title:const Text('I verified this person’s identity outside the app.')),
        const NotePanel('The Administrator role can grant access to others. Access changes require the affected user to sign in again.'),
        if(error!=null) Padding(padding:const EdgeInsets.only(top:12),child:Text(error!,style:TextStyle(color:Theme.of(context).colorScheme.error))),
      ]))),actions:[TextButton(onPressed:busy?null:()=>Navigator.pop(dialogContext),child:const Text('Cancel')),FilledButton(onPressed:busy?null:()async{
        if(status=='active' && user.status!='active' && !verified){setDialogState(()=>error='Confirm identity before activating this account.');return;}
        setDialogState((){busy=true;error=null;});
        try{await ref.read(repositoryProvider).updateUser(user,status:status,roleId:roleId);if(dialogContext.mounted)Navigator.pop(dialogContext,true);}
        on FrontendException catch(e){if(dialogContext.mounted)setDialogState((){error=e.message;busy=false;});}
        catch(_){if(dialogContext.mounted)setDialogState((){error='Access could not be saved.';busy=false;});}
      },child:Text(busy?'Saving…':'Save access'))],
    )));
    if(changed==true && mounted){await ref.read(authProvider.notifier).refreshAccess();if(mounted)_load();}
  }

  /// An administrator creates an active account; the person signs in with this password and should change it.
  Future<void> _createUser() async {
    final name=TextEditingController(), email=TextEditingController(), password=TextEditingController();
    final roles=_roles.where((r)=>r.id!='pending').toList();
    var roleId=roles.any((r)=>r.id=='viewer')?'viewer':(roles.isEmpty?'':roles.first.id), busy=false, hidden=true;
    String? error;
    final created=await showDialog<bool>(context:context,builder:(dialogContext)=>StatefulBuilder(builder:(context,setDialogState)=>AlertDialog(
      title:const Text('Create user'),
      content:SizedBox(width:440,child:SingleChildScrollView(child:Column(mainAxisSize:MainAxisSize.min,crossAxisAlignment:CrossAxisAlignment.stretch,children:[
        TextField(controller:name,enabled:!busy,decoration:const InputDecoration(labelText:'Full name')),
        const SizedBox(height:14),TextField(controller:email,enabled:!busy,keyboardType:TextInputType.emailAddress,decoration:const InputDecoration(labelText:'Email')),
        const SizedBox(height:14),TextField(controller:password,enabled:!busy,obscureText:hidden,decoration:InputDecoration(labelText:'First password (12+ characters)',
          suffixIcon:IconButton(tooltip:hidden?'Show password':'Hide password',onPressed:()=>setDialogState(()=>hidden=!hidden),icon:Icon(hidden?LucideIcons.eye:LucideIcons.eyeOff,size:18)))),
        const SizedBox(height:14),DropdownButtonFormField<String>(initialValue:roleId.isEmpty?null:roleId,isExpanded:true,decoration:const InputDecoration(labelText:'Role'),
          items:roles.map((r)=>DropdownMenuItem(value:r.id,child:Text(r.name,overflow:TextOverflow.ellipsis))).toList(),onChanged:busy?null:(v)=>setDialogState(()=>roleId=v!)),
        const SizedBox(height:14),const NotePanel('The account is active at once. Give the password to the person directly, never in a group chat, and ask them to change it after signing in.'),
        if(error!=null) Padding(padding:const EdgeInsets.only(top:12),child:Text(error!,style:TextStyle(color:Theme.of(context).colorScheme.error))),
      ]))),actions:[TextButton(onPressed:busy?null:()=>Navigator.pop(dialogContext),child:const Text('Cancel')),FilledButton(onPressed:busy?null:()async{
        if(name.text.trim().length<2 || !email.text.contains('@') || password.text.length<12 || roleId.isEmpty){setDialogState(()=>error='Enter a name, an email, a password of 12+ characters and a role.');return;}
        setDialogState((){busy=true;error=null;});
        try{await ref.read(repositoryProvider).createUser(name:name.text,email:email.text,password:password.text,roleId:roleId);if(dialogContext.mounted)Navigator.pop(dialogContext,true);}
        on FrontendException catch(e){if(dialogContext.mounted)setDialogState((){error=e.message;busy=false;});}
        catch(_){if(dialogContext.mounted)setDialogState((){error='The account could not be created.';busy=false;});}
      },child:Text(busy?'Creating…':'Create user'))],
    )));
    await Future<void>.delayed(const Duration(milliseconds:250));
    name.dispose();email.dispose();password.dispose();
    if(created==true && mounted)_load();
  }

  Future<void> _editRole([AccessRole? role]) async {
    final name=TextEditingController(text:role?.name);
    final id=TextEditingController(text:role?.id);
    final selected={...?role?.permissions};
    var busy=false;
    String? error;
    final changed=await showDialog<bool>(context:context,builder:(dialogContext)=>StatefulBuilder(builder:(context,setDialogState)=>AlertDialog(
      title:Text(role==null?'Create role':'Edit ${role.name}'),
      content:SizedBox(width:520,child:SingleChildScrollView(child:Column(mainAxisSize:MainAxisSize.min,crossAxisAlignment:CrossAxisAlignment.stretch,children:[
        TextField(controller:name,enabled:!busy,decoration:const InputDecoration(labelText:'Role name')),
        const SizedBox(height:16),if(role==null)TextField(controller:id,enabled:!busy,decoration:const InputDecoration(labelText:'Role ID',hintText:'warehouse-viewer')),
        const SizedBox(height:18),const NotePanel('App access is required for every feature. User and role management can grant administrative powers.'),
        const SizedBox(height:10),
        for(final entry in accessPermissions.entries)CheckboxListTile(contentPadding:EdgeInsets.zero,value:selected.contains(entry.key),onChanged:busy?null:(value)=>setDialogState((){if(value!){selected.add(entry.key);}else{selected.remove(entry.key);}}),title:Text(entry.value),subtitle:Text(entry.key,style:Theme.of(context).textTheme.bodySmall)),
        if(error!=null)Text(error!,style:TextStyle(color:Theme.of(context).colorScheme.error)),
      ]))),actions:[TextButton(onPressed:busy?null:()=>Navigator.pop(dialogContext),child:const Text('Cancel')),FilledButton(onPressed:busy?null:()async{
        if(name.text.trim().length<2 || name.text.trim().length>80 || !RegExp(r'^[a-z][a-z0-9-]{1,39}$').hasMatch(id.text.trim())){setDialogState(()=>error='Enter a name (2–80 characters) and a lowercase role ID (2–40 letters, digits or hyphens).');return;}
        setDialogState((){busy=true;error=null;});
        try{await ref.read(repositoryProvider).saveRole(id:id.text.trim(),name:name.text.trim(),permissions:selected.toList(),revision:role?.revision);if(dialogContext.mounted)Navigator.pop(dialogContext,true);}
        on FrontendException catch(e){if(dialogContext.mounted)setDialogState((){error=e.message;busy=false;});}
        catch(_){if(dialogContext.mounted)setDialogState((){error='Role could not be saved.';busy=false;});}
      },child:Text(busy?'Saving…':'Save role'))],
    )));
    // Dialog transitions finish before their text controllers are disposed.
    await Future<void>.delayed(const Duration(milliseconds:250));
    name.dispose();id.dispose();
    if(changed==true && mounted){await ref.read(authProvider.notifier).refreshAccess();if(mounted)_load();}
  }
}
