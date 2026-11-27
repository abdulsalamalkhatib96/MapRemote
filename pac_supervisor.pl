#!/usr/bin/perl
# Apple-supplied Perl + networksetup; no third-party executable runs as root.
# Invoked only by an explicitly authorized MapRemote administrator command.
use strict;
use warnings;
use Fcntl qw(:DEFAULT :flock O_NOFOLLOW);
use POSIX qw(setsid _exit);
use File::Temp qw(tempfile);
use JSON::PP;
use IO::Select;
use Time::HiRes qw(sleep);

my $base = '/private/var/db/com.mapremote.proxy';
my $journal = "$base/pac-session.json";
my $native = "$base/snapshot.plist";
my $networksetup = '/usr/sbin/networksetup';
my $mode = shift @ARGV // '';
$ENV{LC_ALL} = 'C';
$ENV{LANG} = 'C';
$ENV{PATH} = '/usr/bin:/bin:/usr/sbin:/sbin';
umask 0077;

sub run_cmd {
    my ($exe, @args) = @_;
    open(my $fh, '-|', $exe, @args) or die "Cannot execute $exe: $!\n";
    local $/;
    my $out = <$fh> // '';
    close($fh) or die "$exe failed: $out\n";
    return $out;
}
sub ns { return run_cmd($networksetup, @_); }
sub field {
    my ($text, $name) = @_;
    return $1 if $text =~ /^\Q$name\E:[ \t]*(.*?)[ \t]*\r?$/mi;
    die "Cannot read network setting $name\n";
}
sub proxy_enabled { return lc(field($_[0], 'Enabled')) eq 'yes'; }
sub pac_settings {
    my ($service) = @_;
    my $s = ns('-getautoproxyurl', $service);
    return (field($s,'URL'), proxy_enabled($s));
}
sub manual_match {
    my ($s, $port) = @_;
    return proxy_enabled($s) && field($s,'Server') eq '127.0.0.1' && field($s,'Port') eq "$port";
}
sub own_inactive_url {
    my ($url) = @_;
    return $url =~ m{\Ahttp://127\.0\.0\.1:[0-9]+/mapremote-proxy\.pac\z};
}
sub services {
    my %enabled;
    my @lines = split /\r?\n/, ns('-listallnetworkservices');
    shift @lines;
    for my $s (@lines) { $enabled{$s}=1 if length($s) && $s !~ /^\*/; }
    my @result;
    my $name;
    for my $line (split /\r?\n/, ns('-listnetworkserviceorder')) {
        if ($line =~ /^\([0-9]+\)\s+(.*)$/) { $name=$1; next; }
        # Only physical en* interfaces, not VPN/PPP or disabled services.
        if (defined($name) && $line =~ /Device:\s*en[0-9]+\)/ && $enabled{$name}) {
            push @result,$name;
        }
        undef $name;
    }
    die "No enabled Wi-Fi or Ethernet network service found\n" unless @result;
    return @result;
}
sub identity {
    my ($pid) = @_;
    return undef unless $pid > 1 && kill(0,$pid);
    my $out = eval { run_cmd('/bin/ps','-p',"$pid",'-o','lstart=','-o','stat=') };
    return undef unless defined($out);
    $out =~ s/^\s+|\s+$//g;
    my @words=split /\s+/, $out;
    return undef if @words != 6 || $words[-1] =~ /Z/;
    return join(' ', @words[0..4]);
}
sub write_journal {
    my ($data)=@_;
    my ($fh,$tmp)=tempfile('pac-XXXXXX',DIR=>$base,UNLINK=>0);
    chmod(0600,$tmp) or die "Cannot protect recovery file\n";
    print {$fh} encode_json($data) or die "Cannot write recovery file\n";
    close($fh) or die "Cannot close recovery file\n";
    rename($tmp,$journal) or die "Cannot commit recovery file\n";
}
sub read_journal {
    open(my $fh,'<',$journal) or die "Cannot read PAC recovery file\n";
    local $/;
    my $data=decode_json(<$fh>);
    close($fh);
    die "Invalid PAC recovery file\n" unless ref($data) eq 'HASH' &&
        own_inactive_url($data->{url}//'') && ($data->{port}//0) =~ /^\d+$/ &&
        $data->{port} >= 1024 && $data->{port} <= 65535 && ref($data->{rows}) eq 'ARRAY';
    return $data;
}
sub restore {
    return unless -e $journal;
    my $data=read_journal();
    for my $row (@{$data->{rows}}) {
        my $s=$row->{service};
        die "Invalid recovery service\n" unless defined($s) && length($s) && $s !~ /[\r\n\0]/;
        my ($url,$enabled)=pac_settings($s);
        # Preserve an independently changed PAC URL; only disable ours.
        if ($enabled && $url eq $data->{url}) {
            ns('-setautoproxystate',$s,'off');
            my ($after,$on)=pac_settings($s);
            die "PAC still enabled for $s\n" if $on && $after eq $data->{url};
        }
        for my $pair (['http','-getwebproxy','-setwebproxystate'],['https','-getsecurewebproxy','-setsecurewebproxystate']) {
            next unless $row->{$pair->[0]};
            my $state=ns($pair->[1],$s);
            if (manual_match($state,$data->{port})) {
                ns($pair->[2],$s,'off');
                die "Stale manual proxy remains enabled for $s\n" if manual_match(ns($pair->[1],$s),$data->{port});
            }
        }
    }
    unlink($journal) or die "Cannot remove restored PAC recovery file\n";
}
sub restore_retry {
    while (-e $journal) {
        eval { restore(); };
        last unless -e $journal;
        sleep 2;
    }
}
sub apply {
    my ($port,$url,$valid)=@_;
    my @rows;
    for my $s (services()) {
        my ($before,$active)=pac_settings($s);
        # Never replace another PAC, even an inactive configured URL.
        die "Another PAC configuration exists for $s; MapRemote will not overwrite it\n"
            if $active || ($before ne '' && $before ne '(null)' && $before ne '(none)' && !own_inactive_url($before));
        my $auto=ns('-getproxyautodiscovery',$s);
        die "Cannot determine automatic proxy discovery for $s\n" unless $auto =~ /:\s*(On|Off)\s*$/i;
        die "Automatic proxy discovery is active for $s\n" if lc($1) eq 'on';
        die "SOCKS proxy is active for $s\n" if proxy_enabled(ns('-getsocksfirewallproxy',$s));
        my %row=(service=>$s);
        for my $pair (['http','-getwebproxy'],['https','-getsecurewebproxy']) {
            my $state=ns($pair->[1],$s);
            die "Another manual proxy is active for $s\n" if proxy_enabled($state) && !manual_match($state,$port);
            $row{$pair->[0]}=manual_match($state,$port)?1:0;
        }
        push @rows,\%row;
    }
    die "Proxy startup cancelled\n" unless $valid->();
    write_journal({url=>$url,port=>$port,rows=>\@rows});
    for my $row (@rows) {
        die "Proxy startup cancelled\n" unless $valid->();
        my $s=$row->{service};
        ns('-setwebproxystate',$s,'off') if $row->{http};
        ns('-setsecurewebproxystate',$s,'off') if $row->{https};
        ns('-setautoproxyurl',$s,$url);
        ns('-setautoproxystate',$s,'on');
        my ($actual,$on)=pac_settings($s);
        die "PAC activation failed for $s\n" unless $actual eq $url && $on;
    }
}
if ($mode eq 'self-test') {
    die "PAC parser failed\n" unless manual_match("Enabled: Yes\nServer: 127.0.0.1\nPort: 9090\n",9090);
    die "PAC parser failed\n" if manual_match("Enabled: No\nServer: 127.0.0.1\nPort: 9090\n",9090);
    die "PAC URL check failed\n" unless own_inactive_url('http://127.0.0.1:49152/mapremote-proxy.pac');
    die "PAC URL check failed\n" if own_inactive_url('http://example.org/mapremote-proxy.pac');
    print "MapRemote PAC supervisor OK\n";
    exit 0;
}
die "Administrator permission required\n" unless $> == 0;
die "Invalid operation\n" unless $mode eq 'run' || $mode eq 'recover';
if (!-e $base) { mkdir($base,0755) or die "Cannot create recovery directory\n"; chmod(0755,$base) or die "Cannot expose recovery status\n"; }
die "Unsafe recovery directory\n" if -l $base || !-d $base || (stat($base))[4] != 0 || ((stat($base))[2] & 0022);
sysopen(my $lock,"$base/lock",O_CREAT|O_RDWR|O_NOFOLLOW,0600) or die "Cannot open recovery lock\n";
flock($lock,LOCK_EX|LOCK_NB) or die "Another MapRemote network session is active\n";
die "Previous native recovery journal exists; restore it before changing network settings\n" if -e $native;
restore();
if ($mode eq 'recover') { print "OK\n"; exit 0; }
my ($controller,$engine,$port,$pacport)=@ARGV;
die "Invalid proxy session\n" unless @ARGV==4 && !grep { !defined($_) || $_ !~ /\A[0-9]+\z/ } @ARGV;
die "Invalid port\n" unless $port>=1024 && $port<=65535 && $pacport>=1024 && $pacport<=65535;
my $controller_id=identity($controller);
my $engine_id=identity($engine);
die "Expired proxy session\n" unless defined($controller_id) && defined($engine_id);
my $valid=sub {
    my $c=identity($controller);
    my $e=identity($engine);
    return defined($c) && defined($e) && $c eq $controller_id && $e eq $engine_id;
};
my $url="http://127.0.0.1:$pacport/mapremote-proxy.pac";
pipe(my $reader,my $writer) or die "Cannot create readiness pipe\n";
my $pid=fork();
die "Cannot start PAC supervisor\n" unless defined($pid);
if ($pid) {
    close($writer); close($lock);
    my $select=IO::Select->new($reader);
    die "PAC supervisor readiness timed out\n" unless $select->can_read(35);
    my $result=<$reader>//'';
    close($reader);
    die "PAC supervisor: $result\n" unless $result eq "OK\n";
    print $result;
    exit 0;
}
close($reader);
setsid() >= 0 or _exit(1);
open(STDIN,'<','/dev/null') or _exit(1);
open(STDOUT,'>','/dev/null') or _exit(1);
open(STDERR,'>','/dev/null') or _exit(1);
$SIG{PIPE}='IGNORE';
$SIG{HUP}='IGNORE';
my $stopping=0;
$SIG{TERM}=sub { $stopping=1; };
$SIG{INT}=sub { $stopping=1; };
my $ok=eval { apply($port,$url,$valid); die "Proxy startup cancelled\n" unless $valid->(); 1 };
if (!$ok) {
    my $err=$@ || 'Unknown activation failure';
    $err =~ s/[\r\n]+/ /g;
    print {$writer} "ERROR: $err\n";
    close($writer);
    restore_retry();
    _exit(1);
}
print {$writer} "OK\n";
close($writer);
my $missed=0;
while (!$stopping) {
    last unless kill(0,$controller) && kill(0,$engine);
    if ($valid->()) { $missed=0; } else { last if ++$missed >= 3; }
    sleep 1;
}
restore_retry();
_exit(0);
