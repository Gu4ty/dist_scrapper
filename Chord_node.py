import zmq
import sys
import time
import json
import random
import threading
import select

def split_ip(ip):
    return ip.split(':')

class Chord_Node:
    #=====Requests strings=====
    CPF = 'closest_preceding_finger'
    FS = 'find_successor'
    UPDATE_PRED = 'update_predeccessor'
    UFT = 'update_finger_table'
    RFT = 'request_finger_table'
    RSL = 'request_succesor_list'
    NOTIFY = 'notify'
    ALIVE = 'alive'
    #==========================
    
    def __init__(self, id, my_ip, m ,entry_point = None):
        
        self.context = zmq.Context()
        ip,port = split_ip(my_ip)
        self.s_rep = self.context.socket(zmq.REP)
        self.s_rep.bind("tcp://%s:%s" %(ip,port))

        self.id = id
        self.ip = my_ip
        self.m = m
        #finger[i] = node with id >= id + 2^(i-1)
        self.finger = [(self.id,self.ip) for _ in range(m+1)] #finger[0] = Predecessor
        self.succesors = [(self.id,self.ip) for _ in range(m)]
        if entry_point:
            self.join(entry_point)
        
        

        #-----------handlers-----------
        self.handlers = {}
        self.handlers[Chord_Node.CPF] = self.request_closest_preceding_finger_handler
        self.handlers[Chord_Node.FS] =  self.request_successor_handler
        self.handlers[Chord_Node.UPDATE_PRED] = self.request_update_predeccessor_handler
        self.handlers[Chord_Node.UFT] = self.request_update_finger_handler
        self.handlers[Chord_Node.RFT] = self.request_finger_table_handler
        self.handlers[Chord_Node.NOTIFY] = self.request_notify_handler
        self.handlers[Chord_Node.ALIVE] = self.request_is_alive_handler
        self.handlers[Chord_Node.RSL] = self.request_succesor_list_handler
        #------------------------------

        self.lock_finger = threading.Lock()
        self.lock_succesors = threading.Lock()
        threading.Thread(target=self.infinit_fix_fingers, args=()).start()
        threading.Thread(target=self.infinit_stabilize, args=()).start()
        threading.Thread(target=self.infinit_fix_succesors, args=()).start()
        self.run()


    #============Join node============
    def join(self,entry_point):
        self.init_finger_table(entry_point)
        self.succesors = [self.finger[1] for _ in range(self.m)]
        self.update_others()
             

    def init_finger_table(self, ip):
        
        node_succ = self.request_successor(ip, self.start_idx(1))
        if not node_succ:
            print('Unstable network, try again later')
            exit()
        self.finger[1] =  (node_succ['id'], node_succ['ip'])
        self.finger[0] = node_succ['fg'][0] 
        
        self.request_update_predeccessor(node_succ['ip'])
        for i in range(1,self.m):
            node =  self.finger[i] #id,ip
            start = self.start_idx(i+1)
            if self.inbetween(start,self.id,True , node[0], False ):
                self.finger[i+1] = self.finger[i]
            else:
                succ_node = self.request_successor(ip,start)
                if not succ_node:
                    print('Unstable network, try again later')
                    exit()
                self.finger[i+1] = (succ_node['id'], succ_node['ip'])

    def update_others(self):
        for i in range(1,self.m+1):
           
            node = self.find_predecessor( (self.id - (2**(i-1))   + 2**self.m ) % 2**self.m   )
            if node['id'] != self.id:
                self.request_update_finger((self.id,self.ip),node['ip'], i)
                
        
                
    def update_finger_table(self,n,i):
        node =  self.finger[i]
        if self.inbetween(n[0], self.id,True , node[0],False ):
            self.finger[i] = n
            pred_node = self.finger[0]
            if pred_node[0] != n[0]:
                self.request_update_finger(n,pred_node[1], i)
               
   
    #============End Join node============

    #============Stabilization============
    def stabilize(self):
        self.lock_finger.acquire()
        successor_finger_table = self.request_finger_table(self.finger[1][1])
        if successor_finger_table:
            
            predeccessor = successor_finger_table[0]
            if self.inbetween(predeccessor[0], self.id,False , self.finger[1][0],False):
                self.finger[1] = predeccessor
                self.succesors[0]= predeccessor
           
        else:
            suc_node = next( (n for n in self.succesors  if self.is_alive(n[1]) ) , None) 
            if suc_node:
                self.finger[1] = suc_node
        
        
        self.request_notify(self.finger[1][1])
        
        self.lock_finger.release()
        
    
    def fix_fingers(self):
       
        self.lock_finger.acquire()
        i = random.randint(1,self.m)
        node = self.find_succesor(self.start_idx(i))
        if node:
            self.finger[i] = (node['id'], node['ip'])
        self.lock_finger.release()
    
    def fix_succesors(self):
        self.lock_succesors.acquire()
        self.succesors[0]= self.finger[1]
        i = random.randint(1,self.m-1)
        succesor_node = self.succesors[i-1]
        node = self.find_succesor( (succesor_node[0] + 1) % (2**self.m) )
        if  node:
            self.succesors[i] = ( node['id'], node['ip'] )
        self.lock_succesors.release()

    def infinit_stabilize(self):
        while True:
            print("\033c")
            self.print_me()
            self.stabilize()
            time.sleep(1)

    def infinit_fix_fingers(self):
        while True:
            self.fix_fingers()
            time.sleep(1)
    
    def infinit_fix_succesors(self):
        while True:
            self.fix_succesors()
            time.sleep(1)
            
    #============End Stabilization============

    def find_succesor(self, idx):
        
        node = self.find_predecessor(idx)
        if not node:
            return None
        succesors = self.succesors
        if node['id'] != self.id:
            succesors = self.request_succesor_list(node['ip'])
            if not succesors:
                return None
        next_node = next( (n for n in succesors  if self.is_alive(n[1]) ) , None)
        if not next_node:
            return None
        if next_node[0] == self.id:
            return self.to_dicctionary()
        
        node_succ_finger = self.request_finger_table(next_node[1])
        if node_succ_finger:
            return {'id': next_node[0], 'ip': next_node[1], 'fg': node_succ_finger}

        return None

    def find_predecessor(self, idx):
        node = (self.id, self.ip)
        omit = []
        while(True):
            id = node[0]
            ip = node[1]
            ft = self.request_finger_table(node[1])
            if not ft:
                return None
            node_succ_id, node_succ_ip = ft[1]
            if self.inbetween(idx, id,False, node_succ_id,True ):
                return {'id': node[0], 'ip': node[1], 'fg': ft}
            if id == self.id :
                node = self.closest_preceding_finger(idx, omit)
            else:
                node = self.request_closest_preceding_finger(node[1],idx,omit)
                if not node:
                    return None

            alive = self.is_alive(node[1])
            while(not alive):
                omit.append(node[0])
                if id == self.id :
                    node = self.closest_preceding_finger(idx, omit)
                else:
                    node = self.request_closest_preceding_finger(ip,idx,omit)
                    if not node:
                        return None
                alive = self.is_alive(node[1])

            if node[0] == id:
                return {'id': node[0], 'ip': node[1], 'fg': ft}

    def closest_preceding_finger(self,idx , omit):
        for i in reversed(range(1,self.m+1)):
            node_id,node_ip = self.finger[i]
            if self.inbetween(node_id, self.id,False, idx,False ):
                if node_id not in omit:
                    return (node_id, node_ip)
        
        closest = next( (n for n in reversed(self.succesors)  if n[0] not in omit and self.inbetween(n[0], self.id,False, idx, False) ) , None)
        if closest:
            return closest
        return (self.id,self.ip)

    #============Send Requests============
    
    def request_successor(self, ip_port, idx):
        response = self.send_request(ip_port, Chord_Node.FS, str(idx))
        if response:
            return json.loads(response)
        return None
    
    def request_closest_preceding_finger(self, ip_port,idx, omit):
        response = self.send_request(ip_port, Chord_Node.CPF, str(idx) + " " + json.dumps(omit))
        if response:
            node = json.loads(response)
            return node
        return None

    def request_update_predeccessor(self, ip_port):
        response = self.send_request(ip_port,Chord_Node.UPDATE_PRED, json.dumps((self.id,self.ip)) )
        if response:
            return "OK"
        return None

    def request_update_finger(self,node,ip_port,i):
        response = self.send_request(ip_port,Chord_Node.UFT, json.dumps([node,i] ) )
        if response:
            return "OK"
        return None
    
    def request_finger_table(self, ip_port):
        if self.ip == ip_port:
            return self.finger
        response = self.send_request(ip_port,Chord_Node.RFT, " " )
        if response:
            return json.loads(response)
        return None

    def request_succesor_list(self,ip_port):
        response = self.send_request(ip_port, Chord_Node.RSL, " ")
        if response:
            return json.loads(response)
        return None
    
    def request_notify(self,ip_port):
        response = self.send_request(ip_port,Chord_Node.NOTIFY,json.dumps((self.id,self.ip)) )
        if response:
            return "OK"
        return None
    
    #============End Send Requests============

    #============Handling Requests============
    def request_successor_handler(self, body):
        idx = int(body)
        node = self.find_succesor(idx)
        self.s_rep.send_string(json.dumps(node) )
    
    def request_closest_preceding_finger_handler(self, body):
        idx, omit = body.split(" ",1)
        idx = int(idx)
        omit = json.loads(omit)
        node = self.closest_preceding_finger(idx,omit)
        self.s_rep.send_string(json.dumps(node))
    
    def request_update_predeccessor_handler(self, body):
        self.finger[0] = json.loads(body)
        self.s_rep.send_string('OK')

    def request_update_finger_handler(self, body):
        node, i = json.loads(body)
        self.update_finger_table(node,i)
        self.s_rep.send_string('OK')
       

    def request_finger_table_handler(self, body = None):
        self.s_rep.send_string(json.dumps(self.finger))
    
    def request_succesor_list_handler(self, body):
        self.s_rep.send_string(json.dumps(self.succesors))
    
    def request_notify_handler(self, body):
        p = json.loads(body)
        if self.is_alive(self.finger[0][1]):
            if(self.inbetween(p[0], self.finger[0][0],False, self.id,False  )):
                self.finger[0] = p
        else:
            self.finger[0] = p

        self.s_rep.send_string('OK')
    def request_is_alive_handler(self, body):
        self.s_rep.send_string("OK")
    
    #============End Handling Requests============
    

    #============Utils============
    
    def is_alive(self,ip_port):
        if ip_port == self.ip:
            return "OK"
        return self.send_request(ip_port,Chord_Node.ALIVE, ' ')

    def send_request(self, ip_port, head,body):
        s_req = self.make_req_socket(ip_port)
        s_req.setsockopt( zmq.RCVTIMEO, 1000 ) # milliseconds
        s_req.send_string(head + " " + body)
        try:
            return s_req.recv_string() # response
        except:
            return None # timeout

    def print_me(self):
        print("Node id: ", self.id)
        print("Node ip: ", self.ip)
        print("Predecessor: ", self.finger[0])
        for i in range(1, self.m + 1):
            print(f'Finger[{i}]= (node id: {self.finger[i][0]} , node ip: {self.finger[i][1]} )')
        print("Successors list: ", self.succesors)

    def inbetween(self,key, lwb, lequal, upb, requal):
        
        if key== upb or key == lwb:
                if key == upb:
                    return requal
                if key == lwb:
                    return lequal

        if lwb == upb:
            return True


        if lwb <= upb:
            return key >= lwb and key <= upb
        else:
            return not (key <= lwb and key >= upb  )



    def start_idx(self,k):
        return (self.id + 2**(k-1)) % (2**self.m)

    def to_json(self):
        return json.dumps(self.to_dicctionary())

    def to_dicctionary(self):
        node = {}
        node['id'] = self.id
        node['ip'] = self.ip
        node['fg'] = self.finger
        return node
    
    def make_req_socket(self, ip_port):
        s_req = self.context.socket(zmq.REQ)
        ip, port = split_ip(ip_port)
        s_req.connect("tcp://%s:%s" %(ip,port))
        return s_req
    
    #============end Utils============


    def run(self):
        while(True): 
            
            try:
                req = self.s_rep.recv_string()
                header,body = req.split(" ",1)
                self.handlers[header](body)
            except KeyboardInterrupt:
                break    

def main():
    id = int(sys.argv[1])
    ip = sys.argv[2]
    m = int(sys.argv[3])
    entry = None
    if len(sys.argv) ==5:
        entry = sys.argv[4]
    
    n = Chord_Node(id,ip,m,entry)

if __name__ == "__main__":
    main()