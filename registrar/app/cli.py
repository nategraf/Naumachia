#!/usr/bin/env python3
import argparse
import registrar
import logging

def parse_args():
    parser = argparse.ArgumentParser(
        description = "Manages client certificates and configurations for Naumachia challeneges",
        formatter_class = argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('challenge', help="the short name for the challenge")
    parser.add_argument('--openvpn', metavar='PATH', help="path to the directory for openvpn configurations", default=None)
    parser.add_argument('--easyrsa', metavar='PATH', help="path to the directory containing the easyrsa executable", default=registrar.EASYRSA)
    subparsers = parser.add_subparsers(dest='action', help="what you wish to do with the client config")

    parser_add = subparsers.add_parser('add', help="create a set of certificates for a client")
    parser_add.add_argument('client', help="name of the client")
    parser_add.add_argument('-r', dest="recreate", action='store_true', help="recreate the certificates for this user if they exist")

    parser_get = subparsers.add_parser('get', help="print an openvpn client configuration file for a client")
    parser_get.add_argument('client', help="name of the client")
    parser_get.add_argument('-a', dest="add", action='store_true', help="add a set of certificates if one does not exist already")

    parser_remove = subparsers.add_parser('remove', help="remove the certificates for a client")
    parser_remove.add_argument('client', help="name of the client")

    parser_revoke = subparsers.add_parser('revoke', help="revoke the certificates for a client")
    parser_revoke.add_argument('client', help="name of the client")

    parser_list = subparsers.add_parser('list', help="lists information about clients with certificates")
    parser_list.add_argument('client', nargs='?', default=None, help="name of the client")

    args = parser.parse_args()

    return args

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)

    args = parse_args()

    regi = registrar.Registrar(args.challenge, args.openvpn, args.easyrsa)

    if args.action == 'add':
        if args.recreate:
            regi.remove_cert(args.client)
        regi.add_cert(args.client)

    elif args.action == 'get':
        if args.add:
            regi.add_cert(args.client)
        print(regi.get_config(args.client))

    elif args.action == 'revoke':
        regi.revoke_cert(args.client)

    elif args.action == 'remove':
        regi.remove_cert(args.client)

    elif args.action == 'list':
        for entry in regi.list_certs(args.client):
            print(entry.cn, end=' ')
            if entry.status == registrar.CertificateListing.Status.EXPIRED:
                print("[EXPIRED]", end=' ')
            if entry.status == registrar.CertificateListing.Status.REVOKED:
                print("[REVOKED]", end=' ')
            print()
