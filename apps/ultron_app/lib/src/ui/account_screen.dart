import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import '../app_info.dart';
import '../domain/access.dart';
import '../state/providers.dart';
import 'components.dart';

void showUltronAbout(BuildContext context)=>showAboutDialog(context:context,
  applicationName:AppInfo.name,applicationVersion:AppInfo.version,applicationIcon:const BrandMark(size:40),
  children:const [Text('Developed by ${AppInfo.developer}'),SizedBox(height:12),Text('E-commerce operations, workflows, reports and Phone Work in one workspace.'),SizedBox(height:8),Text('Flutter ${AppInfo.flutterVersion} · Dart ${AppInfo.dartVersion}')]);

class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key,this.pending=false,this.profile=false,this.denied=false});
  final bool pending,profile,denied;
  @override
  Widget build(BuildContext context,WidgetRef ref){
    final session=ref.watch(authProvider);
    final user=session.user;
    final content=PageBody(maxWidth:860,children:[
      if(pending) const Padding(padding:EdgeInsets.only(bottom:35),child:BrandMark(wordmark:true)),
      PageHeading(denied?'Access required':pending?(user?.status=='disabled'?'Account disabled':'Awaiting approval'):profile?'Your account':'Your workspace',
        subtitle:pending?'Your administrator decides your app and agent access.':'Cloudflare account and access settings'),
      Card(child:Padding(padding:const EdgeInsets.all(22),child:Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[
        Text(user?.name??'Account',style:Theme.of(context).textTheme.headlineSmall),const SizedBox(height:5),
        Text(user?.email??''),const SizedBox(height:18),
        Wrap(spacing:8,runSpacing:8,children:[Chip(label:Text(user?.roleName??'No role')),Chip(label:Text(user?.status??'Unavailable'))]),
        const SizedBox(height:12),Text(user?.emailVerified==true?'Email verified':'Email ownership has not been verified. Your administrator must verify your identity before granting access.',style:Theme.of(context).textTheme.bodySmall),
      ]))),const SizedBox(height:20),
      if(pending) const NotePanel('Registration creates an account only. Reports, workflows, Phone Work and agent tools remain blocked until an administrator activates your role. If access was just changed, sign in again.'),
      if(denied) const NotePanel('Your current role does not include this feature. Contact your administrator to request access.'),
      if(!pending && !denied && !profile) ...[
        const NotePanel('User management is connected. Operational reports and agent execution are not connected yet; they will use the same server-enforced permissions.'),
        const SizedBox(height:22),
        for(final destination in <(String,String,String,IconData)>[
          ('User management','/app/admin','users.manage',LucideIcons.users),
          ('Roles & permissions','/app/roles','roles.manage',LucideIcons.shieldCheck),
          ('Reports','/app/reports','reports.read',LucideIcons.chartNoAxesColumnIncreasing),
          ('Agent','/app/agent','agent.chat',LucideIcons.messageCircle),
          ('Phone Work','/app/phone','phone.manage',LucideIcons.smartphone),
        ])if(user?.allows(destination.$3)==true)Card(child:ListTile(leading:Icon(destination.$4,size:20),title:Text(destination.$1),trailing:const Icon(LucideIcons.chevronRight,size:18),onTap:()=>context.go(destination.$2))),
      ],
      if(profile) ...[
        const SectionHeading('Your permissions'),
        for(final permission in user?.permissions??<String>[])ListTile(contentPadding:EdgeInsets.zero,leading:const Icon(LucideIcons.check,size:17),title:Text(accessPermissions[permission]??permission)),
        const NotePanel('This session is held in memory and expires on the server after 12 hours. Closing or reloading the app requires sign-in again. Access changes end affected sessions immediately.'),
        const SizedBox(height:16),
        if(user?.allows('users.manage')==true) ListTile(leading:const Icon(LucideIcons.users),title:const Text('User management'),onTap:()=>context.go('/app/admin')),
        if(user?.allows('roles.manage')==true) ListTile(leading:const Icon(LucideIcons.shieldCheck),title:const Text('Roles & permissions'),onTap:()=>context.go('/app/roles')),
        ListTile(title:const Text('About Ultron'),leading:const Icon(LucideIcons.info),onTap:()=>showUltronAbout(context)),
      ],
      if(session.error!=null)NotePanel(session.error!,warning:true),
      const SizedBox(height:20),
      OutlinedButton.icon(onPressed:session.busy?null:()=>ref.read(authProvider.notifier).refreshAccess(),icon:const Icon(LucideIcons.refreshCw,size:17),label:Text(session.busy?'Checking access…':'Refresh my access')),
      const SizedBox(height:12),
      OutlinedButton.icon(key:const Key('sign-out'),onPressed:()=>ref.read(authProvider.notifier).signOut(),icon:const Icon(LucideIcons.logOut,size:17),label:const Text('Sign out')),
      const SizedBox(height:24),Text('Developed by ${AppInfo.developer}',textAlign:TextAlign.center,style:Theme.of(context).textTheme.bodySmall),
    ]);
    return pending?Scaffold(body:SafeArea(child:content)):content;
  }
}
